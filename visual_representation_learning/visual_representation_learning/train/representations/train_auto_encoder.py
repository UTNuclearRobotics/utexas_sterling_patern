#!/usr/bin/env python3
"""
train_auto_encoder.py

An autoencoder is a type of artificial neural network used to learn 
efficient codings of unlabeled data. 

An autoencoder learns two functions: 
- Encoding function that transforms the input data
- Decoding function that recreates the input data from the encoded representation
"""

import argparse
import os
from datetime import datetime

import numpy as np
import pytorch_lightning as pl
import tensorboard as tb
import tensorflow as tf
import torch
import torch.nn as nn
import torch.nn.functional as F
from pytorch_lightning.callbacks.early_stopping import EarlyStopping
from pytorch_lightning.callbacks.model_checkpoint import ModelCheckpoint

from visual_representation_learning.train.representations.data_loader import MyDataLoader

tf.io.gfile = tb.compat.tensorflow_stub.io.gfile



class AutoEncoder(pl.LightningModule):
    def __init__(self, lr, latent_size, batch_size, weight_decay):
        super(AutoEncoder, self).__init__()
        self.save_hyperparameters("lr", "latent_size", "batch_size", "weight_decay")
        self.lr = lr
        self.latent_size = latent_size
        self.batch_size = batch_size
        self.weight_decay = weight_decay

        # Encoder takes 128x128x3 image and outputs 512 dimensional vector
        self.vencoder = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, stride=2, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(),  # 63 x 63 x 32
            nn.Conv2d(32, 64, kernel_size=3, stride=2, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(),  # 31 x 31 x 64
            nn.Conv2d(64, 128, kernel_size=3, stride=2, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(),  # 15 x 15 x 128
            nn.Conv2d(128, 256, kernel_size=3, stride=2, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(),  # 7 x 7 x 256
            nn.Conv2d(256, 512, kernel_size=5, stride=2, bias=False),
            nn.ReLU(),  # 2 x 2 x 512
            nn.Flatten(),
        )
        # Decoder takes 512 dimensional vector and outputs 128x128x3 image
        self.vdecoder = nn.Sequential(
            nn.ConvTranspose2d(512, 256, kernel_size=3, stride=2, padding=1, output_padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.ConvTranspose2d(256, 128, kernel_size=3, stride=2, padding=1, output_padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.ConvTranspose2d(128, 64, kernel_size=3, stride=2, padding=1, output_padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.ConvTranspose2d(64, 32, kernel_size=3, stride=2, padding=1, output_padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.ConvTranspose2d(32, 32, kernel_size=3, stride=2, padding=1, output_padding=1, bias=False),
            nn.ReLU(),
            nn.ConvTranspose2d(32, 3, kernel_size=3, stride=2, padding=1, output_padding=1),
            nn.Sigmoid(),
        )

        self.iencoder = nn.Sequential(
            nn.Linear(1200, 1024, bias=False),
            nn.BatchNorm1d(1024),
            nn.ReLU(),
            nn.Linear(1024, 1024, bias=False),
            nn.BatchNorm1d(1024),
            nn.ReLU(),
            nn.Linear(1024, 1024, bias=False),
            nn.ReLU(),
            nn.Linear(1024, 2 * 2 * 512),
        )
        self.idecoder = nn.Sequential(
            nn.Linear(2 * 2 * 512, 1024, bias=False),
            nn.BatchNorm1d(1024),
            nn.ReLU(),
            nn.Linear(1024, 1024, bias=False),
            nn.BatchNorm1d(1024),
            nn.ReLU(),
            nn.Linear(1024, 1024, bias=False),
            nn.ReLU(),
            nn.Linear(1024, 1200),
        )

    def forward_pass(self, visual, inertial):
        v_enc = self.vencoder(visual)
        i_enc = self.iencoder(inertial.view(-1, 1200))

        visual_recon = self.vdecoder(v_enc.view(-1, 512, 2, 2))
        inertial_recon = self.idecoder(i_enc.view(-1, 2 * 2 * 512))

        return visual_recon, inertial_recon, v_enc.view(-1, 512 * 2 * 2), i_enc.view(-1, 2 * 2 * 512)

    def training_step(self, batch, batch_idx):
        visual1, _, inertial, _ = batch
        visual_recon, inertial_recon, v_enc, i_enc = self.forward_pass(visual1, inertial)
        recon_loss = F.mse_loss(visual_recon, visual1, reduction="mean") + F.mse_loss(
            inertial_recon, inertial, reduction="mean"
        )
        latent_loss = F.mse_loss(v_enc, i_enc, reduction="mean")

        latent_norm_loss = 1e-3 * torch.norm(v_enc, p=2, dim=1).mean() + 1e-3 * torch.norm(i_enc, p=2, dim=1).mean()

        loss = 100 * recon_loss + latent_loss + latent_norm_loss
        self.log("train_loss", loss, prog_bar=True)
        self.log("train_recon_loss", recon_loss, prog_bar=True)
        self.log("train_latent_loss", latent_loss, prog_bar=True)
        self.log("train_latent_norm_loss", latent_norm_loss, prog_bar=True)
        return loss

    def validation_step(self, batch, batch_idx):
        visual1, _, inertial, _ = batch
        visual_recon, inertial_recon, v_enc, i_enc = self.forward_pass(visual1, inertial)
        recon_loss = F.mse_loss(visual_recon, visual1, reduction="mean") + F.mse_loss(
            inertial_recon, inertial, reduction="mean"
        )
        latent_loss = F.mse_loss(v_enc, i_enc, reduction="mean")

        latent_norm_loss = 1e-3 * torch.norm(v_enc, p=2, dim=1).mean() + 1e-3 * torch.norm(i_enc, p=2, dim=1).mean()

        loss = 100 * recon_loss + latent_loss + latent_norm_loss
        self.log("val_loss", loss, prog_bar=True)
        self.log("val_recon_loss", recon_loss, prog_bar=True)
        self.log("val_latent_loss", latent_loss, prog_bar=True)
        self.log("val_latent_norm_loss", latent_norm_loss, prog_bar=True)
        return loss

    def on_validation_batch_start(self, batch, batch_idx, dataloader_idx):
        if self.current_epoch % 10 == 0:
            visual_patch, visual_patch_2, imu_history, label = batch
            label = np.asarray(label)
            visual_patch = visual_patch.float()
            visual_encoding = self.vencoder(visual_patch.cuda()).view(-1, 512 * 2 * 2)
            # visual_encoding = F.normalize(visual_encoding, dim=1)

            if batch_idx == 0:
                # self.visual_encoding = visual_encoding[:, :]
                # self.visual_patch = visual_patch[:, :, :, :]
                # self.label = label[:]
                self.visual_encoding = [visual_encoding[:, :]]
                self.visual_patch = [visual_patch[:, :, :, :]]
                self.label = label[:]
            else:
                # self.visual_patch = torch.cat((self.visual_patch, visual_patch[:, :, :, :]), dim=0)
                # self.visual_encoding = torch.cat((self.visual_encoding, visual_encoding[:, :]), dim=0)
                # self.label = np.concatenate((self.label, label[:]))
                self.visual_patch.append(visual_patch[:, :, :, :])
                self.visual_encoding.append(visual_encoding[:, :])
                self.label = np.concatenate((self.label, label[:]))

    def on_validation_end(self) -> None:
        if self.current_epoch % 10 == 0:
            self.visual_patch = torch.cat(self.visual_patch, dim=0)
            self.visual_encoding = torch.cat(self.visual_encoding, dim=0)
            idx = np.arange(self.visual_encoding.shape[0])

            # randomize numpy array
            np.random.shuffle(idx)

            self.logger.experiment.add_embedding(
                mat=self.visual_encoding[idx[:2000], :],
                label_img=self.visual_patch[idx[:2000], :, :, :],
                global_step=self.current_epoch,
                metadata=self.label[idx[:2000]],
            )

    def configure_optimizers(self):
        return torch.optim.AdamW(self.parameters(), lr=self.lr, weight_decay=self.weight_decay)


def main():
    print("hi...")

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Train AutoEncoder model")
    parser.add_argument("--config", type=str, default="", help="Dataset config file")
    args = parser.parse_args()

    # Use command line arguments if provided
    if args.config:
        DATA_CONFIG_PATH = args.config

    # Check if the dataset config yaml file exists
    if not os.path.exists(DATA_CONFIG_PATH):
        raise FileNotFoundError(DATA_CONFIG_PATH)

    # Hyperparameters
    BATCH_SIZE = 64
    LR = 3e-4
    WEIGHT_DECAY = 1e-5

    # Set device to GPU if available, otherwise CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Initialize data loader
    dm = MyDataLoader(data_config_path=DATA_CONFIG_PATH, batch_size=BATCH_SIZE)

    # Initialize the AutoEncoder model
    model = AutoEncoder(lr=LR, latent_size=512, weight_decay=WEIGHT_DECAY, batch_size=BATCH_SIZE).to(device)

    # Define callbacks for early stopping and model checkpointing
    early_stopping_cb = EarlyStopping(monitor="val_loss", mode="min", min_delta=0.00, patience=1000)
    model_checkpoint_cb = ModelCheckpoint(
        dirpath="checkpoint/",
        filename=datetime.now().strftime("%d-%m-%Y-%H-%M-%S") + "_",
        monitor="val_loss",
        verbose=True,
    )

    print("Training model...")

    # Initialize the PyTorch Lightning trainer
    trainer = pl.Trainer(
        gpus=list(np.arange(2)),  # Use 2 GPUs
        max_epochs=10000,  # Maximum number of epochs
        callbacks=[model_checkpoint_cb],  # Add callbacks
        log_every_n_steps=10,  # Log every 10 steps
        distributed_backend="ddp",  # Use Distributed Data Parallel
        num_sanity_val_steps=0,  # Number of sanity validation steps
        logger=True,  # Enable logging
    )

    # Start training
    trainer.fit(model, dm)

if __name__ == "__main__":
    main()