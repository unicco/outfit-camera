#!/usr/bin/env python3
"""Train embedding model with hard negatives using Triplet Loss or InfoNCE."""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TripletDataset(Dataset):
    """Dataset for triplet training with hard negatives."""

    def __init__(self, triplets: List[Dict[str, Any]]):
        self.triplets = triplets

    def __len__(self):
        return len(self.triplets)

    def __getitem__(self, idx):
        triplet = self.triplets[idx]

        # Convert embeddings to tensors
        anchor = torch.tensor(triplet["anchor"]["embedding"], dtype=torch.float32)
        positive = torch.tensor(triplet["positive"]["embedding"], dtype=torch.float32)
        negative = torch.tensor(triplet["negative"]["embedding"], dtype=torch.float32)

        return anchor, positive, negative, triplet["metadata"]


class EmbeddingAdapter(nn.Module):
    """埋め込みアダプターネットワーク
    Jina埋め込みを変換して、ハードネガティブをより良く分離する.
    """

    def __init__(
        self, input_dim: int = 1024, hidden_dim: int = 512, output_dim: int = 256
    ):
        super().__init__()

        self.adapter = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, output_dim),
            nn.LayerNorm(output_dim),
        )

        # Initialize weights
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.constant_(m.bias, 0)

    def forward(self, x):
        # Normalize input
        x = F.normalize(x, p=2, dim=1)
        # Apply adapter
        x = self.adapter(x)
        # L2 normalize output
        x = F.normalize(x, p=2, dim=1)
        return x


class TripletLoss(nn.Module):
    """Triplet loss with margin."""

    def __init__(self, margin: float = 0.2):
        super().__init__()
        self.margin = margin

    def forward(self, anchor, positive, negative):
        distance_positive = F.pairwise_distance(anchor, positive, p=2)
        distance_negative = F.pairwise_distance(anchor, negative, p=2)
        losses = F.relu(distance_positive - distance_negative + self.margin)
        return losses.mean()


class InfoNCELoss(nn.Module):
    """InfoNCE loss for contrastive learning."""

    def __init__(self, temperature: float = 0.07):
        super().__init__()
        self.temperature = temperature

    def forward(self, anchor, positive, negatives):
        """Args:
        anchor: (batch_size, dim)
        positive: (batch_size, dim)
        negatives: (batch_size, num_negatives, dim).

        """
        batch_size = anchor.shape[0]

        # Compute similarities
        pos_sim = F.cosine_similarity(anchor, positive, dim=1) / self.temperature

        # Reshape for negative similarities
        anchor_expanded = anchor.unsqueeze(1)  # (batch_size, 1, dim)
        neg_sim = (
            F.cosine_similarity(anchor_expanded, negatives, dim=2) / self.temperature
        )

        # Concatenate positive and negative similarities
        logits = torch.cat([pos_sim.unsqueeze(1), neg_sim], dim=1)

        # Labels: positive is at index 0
        labels = torch.zeros(batch_size, dtype=torch.long, device=anchor.device)

        return F.cross_entropy(logits, labels)


class HardNegativeTrainer:
    """Trainer for embedding model with hard negatives."""

    def __init__(
        self,
        model: nn.Module,
        loss_type: str = "triplet",
        learning_rate: float = 1e-4,
        margin: float = 0.2,
        temperature: float = 0.07,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
    ):

        self.model = model.to(device)
        self.device = device
        self.loss_type = loss_type

        # Loss function
        if loss_type == "triplet":
            self.criterion = TripletLoss(margin=margin)
        elif loss_type == "infonce":
            self.criterion = InfoNCELoss(temperature=temperature)
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")

        # Optimizer
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=100, eta_min=1e-6
        )

        self.train_losses = []
        self.val_losses = []

    def train_epoch(self, dataloader: DataLoader) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0
        num_batches = 0

        for batch in tqdm(dataloader, desc="Training"):
            anchor, positive, negative, _ = batch

            # Move to device
            anchor = anchor.to(self.device)
            positive = positive.to(self.device)
            negative = negative.to(self.device)

            # Forward pass
            anchor_emb = self.model(anchor)
            positive_emb = self.model(positive)
            negative_emb = self.model(negative)

            # Compute loss
            if self.loss_type == "triplet":
                loss = self.criterion(anchor_emb, positive_emb, negative_emb)
            else:  # infonce
                # For InfoNCE, we need to reshape negatives
                negative_emb = negative_emb.unsqueeze(1)  # Add num_negatives dimension
                loss = self.criterion(anchor_emb, positive_emb, negative_emb)

            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        avg_loss = total_loss / num_batches
        self.train_losses.append(avg_loss)
        return avg_loss

    def validate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0
        num_batches = 0

        # Metrics
        correct_closer = 0  # Count where positive is closer than negative
        total_samples = 0

        with torch.no_grad():
            for batch in tqdm(dataloader, desc="Validation"):
                anchor, positive, negative, _ = batch

                # Move to device
                anchor = anchor.to(self.device)
                positive = positive.to(self.device)
                negative = negative.to(self.device)

                # Forward pass
                anchor_emb = self.model(anchor)
                positive_emb = self.model(positive)
                negative_emb = self.model(negative)

                # Compute loss
                if self.loss_type == "triplet":
                    loss = self.criterion(anchor_emb, positive_emb, negative_emb)
                else:
                    negative_emb = negative_emb.unsqueeze(1)
                    loss = self.criterion(anchor_emb, positive_emb, negative_emb)

                total_loss += loss.item()
                num_batches += 1

                # Compute accuracy metric
                pos_dist = F.pairwise_distance(anchor_emb, positive_emb, p=2)
                neg_dist = F.pairwise_distance(anchor_emb, negative_emb.squeeze(1), p=2)
                correct_closer += (pos_dist < neg_dist).sum().item()
                total_samples += anchor.size(0)

        avg_loss = total_loss / num_batches
        accuracy = correct_closer / total_samples
        self.val_losses.append(avg_loss)

        return {"loss": avg_loss, "accuracy": accuracy}

    def save_checkpoint(self, path: str, epoch: int, best_loss: float):
        """Save model checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "best_loss": best_loss,
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
        }
        torch.save(checkpoint, path)

    def load_checkpoint(self, path: str) -> Dict[str, Any]:
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        self.train_losses = checkpoint.get("train_losses", [])
        self.val_losses = checkpoint.get("val_losses", [])
        return checkpoint


def load_triplets(triplet_path: str) -> List[Dict[str, Any]]:
    """Load triplets from JSON file."""
    with open(triplet_path, "r") as f:
        triplets = json.load(f)

    # Validate triplets
    valid_triplets = []
    for triplet in triplets:
        if all(key in triplet for key in ["anchor", "positive", "negative"]):
            valid_triplets.append(triplet)

    return valid_triplets


def split_data(
    triplets: List[Dict[str, Any]], val_ratio: float = 0.2
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split triplets into train and validation sets."""
    np.random.shuffle(triplets)
    split_idx = int(len(triplets) * (1 - val_ratio))
    return triplets[:split_idx], triplets[split_idx:]


def main():
    parser = argparse.ArgumentParser(
        description="Train embedding adapter with hard negatives"
    )
    parser.add_argument(
        "--triplets", type=str, required=True, help="Path to triplets JSON file"
    )
    parser.add_argument(
        "--loss",
        type=str,
        default="triplet",
        choices=["triplet", "infonce"],
        help="Loss function type",
    )
    parser.add_argument(
        "--epochs", type=int, default=50, help="Number of training epochs"
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument(
        "--learning-rate", type=float, default=1e-4, help="Learning rate"
    )
    parser.add_argument(
        "--margin", type=float, default=0.2, help="Margin for triplet loss"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.07, help="Temperature for InfoNCE"
    )
    parser.add_argument("--hidden-dim", type=int, default=512, help="Hidden dimension")
    parser.add_argument("--output-dim", type=int, default=256, help="Output dimension")
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="checkpoints",
        help="Directory to save checkpoints",
    )
    parser.add_argument("--resume", type=str, help="Resume from checkpoint")

    args = parser.parse_args()

    # Load triplets
    print(f"\n📊 Loading triplets from {args.triplets}...")
    triplets = load_triplets(args.triplets)
    print(f"   Loaded {len(triplets)} triplets")

    # Split data
    train_triplets, val_triplets = split_data(triplets)
    print(f"   Train: {len(train_triplets)}, Val: {len(val_triplets)}")

    # Create datasets and dataloaders
    train_dataset = TripletDataset(train_triplets)
    val_dataset = TripletDataset(val_triplets)

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=4
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=4
    )

    # Create model
    model = EmbeddingAdapter(
        input_dim=1024,  # Jina embedding dimension
        hidden_dim=args.hidden_dim,
        output_dim=args.output_dim,
    )

    # Create trainer
    trainer = HardNegativeTrainer(
        model=model,
        loss_type=args.loss,
        learning_rate=args.learning_rate,
        margin=args.margin,
        temperature=args.temperature,
    )

    # Resume from checkpoint if specified
    start_epoch = 0
    best_val_loss = float("inf")
    if args.resume:
        print(f"\n📂 Resuming from checkpoint: {args.resume}")
        checkpoint = trainer.load_checkpoint(args.resume)
        start_epoch = checkpoint["epoch"]
        best_val_loss = checkpoint["best_loss"]

    # Training loop
    print("\n🏃 Starting training...")
    print(f"   Loss: {args.loss}")
    print(f"   Epochs: {args.epochs}")
    print(f"   Batch size: {args.batch_size}")

    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(start_epoch, args.epochs):
        print(f"\n📍 Epoch {epoch + 1}/{args.epochs}")

        # Train
        train_loss = trainer.train_epoch(train_loader)
        print(f"   Train loss: {train_loss:.4f}")

        # Validate
        val_metrics = trainer.validate(val_loader)
        print(f"   Val loss: {val_metrics['loss']:.4f}")
        print(f"   Val accuracy: {val_metrics['accuracy']:.2%}")

        # Learning rate scheduling
        trainer.scheduler.step()

        # Save checkpoint if best
        if val_metrics["loss"] < best_val_loss:
            best_val_loss = val_metrics["loss"]
            checkpoint_path = checkpoint_dir / "best_model.pth"
            trainer.save_checkpoint(checkpoint_path, epoch + 1, best_val_loss)
            print(f"   💾 Saved best model (loss: {best_val_loss:.4f})")

        # Save periodic checkpoint
        if (epoch + 1) % 10 == 0:
            checkpoint_path = checkpoint_dir / f"checkpoint_epoch_{epoch + 1}.pth"
            trainer.save_checkpoint(checkpoint_path, epoch + 1, best_val_loss)

    print("\n✅ Training completed!")
    print(f"   Best validation loss: {best_val_loss:.4f}")

    # Save final model
    final_path = checkpoint_dir / "final_model.pth"
    trainer.save_checkpoint(final_path, args.epochs, best_val_loss)
    print(f"   💾 Saved final model to: {final_path}")


if __name__ == "__main__":
    main()
