# 開発環境セットアップ (Windows/Linux)

## 前提条件

- Python 3.11以上
- pip
- git

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd reflect-app
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env` ファイルが既に存在する場合は、APIキーが正しく設定されているか確認してください。

存在しない場合:
```bash
cp .env.example .env
```

`.env` ファイルを編集し、Anthropic APIキーを設定:
```
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
```

APIキーは https://console.anthropic.com/ から取得できます。

### 4. アプリケーションの起動

```bash
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

## データ保存

すべてのデータは `data/` ディレクトリにローカル保存されます:

- `data/profile.json` - レベル・経験値・スキル情報
- `data/diaries/YYYY-MM-DD.json` - 日ごとの振り返り記録

初回起動時にこれらのディレクトリとファイルは自動的に作成されます。

## トラブルシューティング

### ポートが既に使用されている場合

```bash
streamlit run app.py --server.port 8502
```

### パッケージのインストールでエラーが出る場合

仮想環境を使用することをお勧めします:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# または
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```
