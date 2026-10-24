"""The field classifier's network (needs torch + transformers).

Kept apart from services/classifier.py so the backend only loads torch (~30 s)
when the classifier is actually switched on. Used by ml/classifier/train.py too.
"""

import json
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer


class FieldClassifier(nn.Module):
    """MiniLM encoder -> average of token vectors -> dropout -> linear layer over the labels."""

    def __init__(self, encoder, n_labels: int, dropout: float = 0.1):
        super().__init__()
        self.encoder = encoder
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(encoder.config.hidden_size, n_labels)

    def forward(self, input_ids, attention_mask, **_):
        tokens = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (tokens * mask).sum(1) / mask.sum(1).clamp(min=1e-9)  # mean over real tokens, not padding
        return self.head(self.dropout(pooled))

    def save(self, out_dir: Path, tokenizer, labels: list[str], meta: dict) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.encoder.save_pretrained(out_dir / "encoder")
        tokenizer.save_pretrained(out_dir / "encoder")
        torch.save(self.head.state_dict(), out_dir / "head.pt")
        (out_dir / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf8")
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf8")

    @classmethod
    def load(cls, model_dir: Path):
        labels = json.loads((model_dir / "labels.json").read_text(encoding="utf8"))
        encoder = AutoModel.from_pretrained(model_dir / "encoder")
        model = cls(encoder, len(labels))
        model.head.load_state_dict(torch.load(model_dir / "head.pt", map_location="cpu"))
        model.eval()
        return model, AutoTokenizer.from_pretrained(model_dir / "encoder"), labels


def predict_texts(model, tokenizer, labels, texts: list[str], max_tokens: int) -> list[tuple[str, float]]:
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            batch = tokenizer(texts[i:i + 64], padding=True, truncation=True, max_length=max_tokens, return_tensors="pt")
            probs = torch.softmax(model(**batch), dim=-1)
            conf, idx = probs.max(dim=-1)
            out += [(labels[j], float(c)) for j, c in zip(idx.tolist(), conf.tolist())]
    return out
