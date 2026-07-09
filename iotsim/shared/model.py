import torch
import torch.nn as nn


class CNNLSTMModel(nn.Module):

    def __init__(self):
        super(CNNLSTMModel, self).__init__()

        self.conv1 = nn.Conv1d(
            in_channels=46,
            out_channels=64,
            kernel_size=3,
            padding=1
        )
        self.bn1 = nn.BatchNorm1d(64)

        self.conv2 = nn.Conv1d(
            in_channels=64,
            out_channels=128,
            kernel_size=3,
            padding=1
        )
        self.bn2 = nn.BatchNorm1d(128)

        self.relu = nn.ReLU()

        self.lstm = nn.LSTM(
            input_size=128,
            hidden_size=128,
            num_layers=2,
            batch_first=True,
            bidirectional=True
        )

        self.classifier = nn.Sequential(
            nn.Linear(256, 128),   # 0
            nn.ReLU(),             # 1
            nn.Dropout(0.3),       # 2
            nn.Linear(128, 64),    # 3
            nn.ReLU(),             # 4
            nn.Dropout(0.3),       # 5
            nn.Linear(64, 1),      # 6
        )

        self.sigmoid = nn.Sigmoid()

    def forward(self, x):

        # x shape: (batch, seq_len, 46)

        x = x.permute(0, 2, 1)          # (batch, 46, seq_len)

        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)                # (batch, 128, seq_len)

        x = x.permute(0, 2, 1)          # (batch, seq_len, 128)

        x, _ = self.lstm(x)             # (batch, seq_len, 256)

        x = x[:, -1, :]                 # last timestep, (batch, 256)

        x = self.classifier(x)          # (batch, 1)

        x = self.sigmoid(x)

        return x