# weather-power-demand-pipeline

ELT pipeline joining Japan's hourly power demand with weather data — Python, GCS, BigQuery, dbt, Looker Studio

> 🚧 Work in progress

## Overview

電力需要実績と気象データを定期的に取り込み、BigQuery 上で dbt により結合・集計し、
Looker Studio で可視化するデータ基盤です。

## Architecture

```
[Power demand CSV]   [Weather API]
        │                  │
        └── Python ingestion ──┘
                  │
                  ▼
          GCS (raw files)
                  │
                  ▼
   BigQuery: raw → staging → mart  (dbt)
                  │
                  ▼
            Looker Studio
```

## Repository structure

```
.
├── ingestion/          # データ取得処理（Python）
├── dbt/                # dbt プロジェクト（staging / mart）
├── infra/              # Terraform（GCP リソース）
├── docs/               # 設計ドキュメント
└── .github/workflows/  # CI / 定期実行
```

## Data sources

- 電力需要：東京電力パワーグリッド「でんき予報」過去実績
- 気象：Open-Meteo Historical Weather API

（出典表記・利用条件は実装時に追記）

## License

[MIT](LICENSE)
