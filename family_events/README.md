# 家族イベント・出産・育児ディレクトリ

家族に関する記録や情報をまとめるディレクトリです。

## 構成

```
family_events/
├── events/          # 家族のイベント記録（記念日、行事、旅行など）
└── birth_childcare/ # 出産・育児に関する記録・情報
```

## events/ の使い方

家族のイベントをJSON形式で記録します。

例: `events/2026-04-05_花見.json`

```json
{
  "date": "2026-04-05",
  "title": "家族で花見",
  "members": ["パパ", "ママ"],
  "notes": "上野公園で花見。満開だった。"
}
```

## birth_childcare/ の使い方

出産・育児に関する記録をJSON形式で保存します。

例: `birth_childcare/成長記録.json`

```json
{
  "name": "お子さんの名前",
  "birth_date": "YYYY-MM-DD",
  "records": [
    {
      "date": "YYYY-MM-DD",
      "age_months": 1,
      "weight_kg": 4.5,
      "height_cm": 55.0,
      "notes": "メモ"
    }
  ]
}
```
