# Windows 社用PC 開発環境セットアップ手順

社用PC（Windows）でClaude Codeを使った開発ができる環境を構築する手順です。

---

## 前提条件

- Windows 10 / 11
- 管理者権限があること（インストール作業に必要）
- インターネット接続があること

---

## 1. パッケージマネージャ（winget）の確認

Windows 10/11には`winget`が標準搭載されています。PowerShellで確認：

```powershell
winget --version
```

表示されない場合は、Microsoft Storeから「アプリ インストーラー」を更新してください。

---

## 2. Git のインストール

```powershell
winget install Git.Git
```

インストール後、**PowerShellを再起動**してから確認：

```powershell
git --version
```

### Git初期設定

```powershell
git config --global user.name "あなたの名前"
git config --global user.email "your-email@seaos.co.jp"
git config --global core.autocrlf true
git config --global init.defaultBranch main
```

> **注意**: `core.autocrlf true` はWindowsでの改行コード問題を防ぎます。

---

## 3. Node.js のインストール（Claude Code に必要）

Claude CodeはNode.js上で動作するため、Node.jsが必要です。

```powershell
winget install OpenJS.NodeJS.LTS
```

PowerShellを再起動して確認：

```powershell
node --version   # v20.x.x 以上
npm --version
```

---

## 4. Python のインストール（プロジェクトで使う場合）

WMSシステム等でPythonを使う場合：

```powershell
winget install Python.Python.3.12
```

PowerShellを再起動して確認：

```powershell
python --version
pip --version
```

### Python仮想環境の使い方

プロジェクトごとに仮想環境を作ることを推奨：

```powershell
# プロジェクトディレクトリで実行
python -m venv .venv

# 仮想環境の有効化
.venv\Scripts\Activate.ps1

# 仮想環境の無効化
deactivate
```

> **PowerShellの実行ポリシーエラーが出た場合：**
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## 5. Visual Studio Code のインストール

```powershell
winget install Microsoft.VisualStudioCode
```

### おすすめ拡張機能

VSCodeを起動後、以下の拡張機能をインストール：

| 拡張機能 | ID | 用途 |
|---|---|---|
| Japanese Language Pack | `MS-CEINTL.vscode-language-pack-ja` | 日本語化 |
| Python | `ms-python.python` | Python開発 |
| GitLens | `eamodio.gitlens` | Git履歴の可視化 |
| Claude Code | （後述） | AI支援 |

コマンドラインから一括インストール：

```powershell
code --install-extension MS-CEINTL.vscode-language-pack-ja
code --install-extension ms-python.python
code --install-extension eamodio.gitlens
```

---

## 6. Claude Code のインストール

### 6-1. npmでインストール

```powershell
npm install -g @anthropic-ai/claude-code
```

確認：

```powershell
claude --version
```

### 6-2. Anthropic APIキーの設定

1. https://console.anthropic.com/ にアクセス
2. APIキーを発行
3. 初回起動時に `claude` コマンドを実行するとAPIキー入力を求められます

または、環境変数で事前設定：

```powershell
# ユーザー環境変数に永続的に設定
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-xxxxx", "User")
```

### 6-3. 動作確認

```powershell
claude
```

対話画面が起動すれば成功です。`/help` でコマンド一覧を確認できます。

---

## 7. GitHub の設定

### SSH鍵の生成と登録

```powershell
ssh-keygen -t ed25519 -C "your-email@seaos.co.jp"
```

公開鍵をコピー：

```powershell
Get-Content ~/.ssh/id_ed25519.pub | clip
```

GitHub（https://github.com/settings/keys）に貼り付けて登録。

### 接続確認

```powershell
ssh -T git@github.com
```

`Hi username! You've been authenticated` と表示されればOK。

---

## 8. プロジェクトのクローンと実行

### リポジトリをクローン

```powershell
cd ~\Documents
git clone git@github.com:niibori-yoshiki/seaos-workspace.git
cd seaos-workspace
```

### （例）Python プロジェクトの場合

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## トラブルシューティング

### PowerShellでスクリプト実行がブロックされる

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### gitコマンドが認識されない

PowerShellを再起動するか、PATHに `C:\Program Files\Git\cmd` を追加。

### nodeコマンドが認識されない

PowerShellを再起動するか、PATHに Node.js のインストールパスを追加。

### 社内プロキシでnpm/gitが繋がらない

```powershell
# npm プロキシ設定
npm config set proxy http://proxy.example.com:8080
npm config set https-proxy http://proxy.example.com:8080

# git プロキシ設定
git config --global http.proxy http://proxy.example.com:8080
git config --global https.proxy http://proxy.example.com:8080
```

> プロキシのURLは社内IT部門に確認してください。

### Claude Codeが起動しない

- Node.js v20以上が必要です。`node --version` で確認
- `npm install -g @anthropic-ai/claude-code` を再実行
- APIキーが正しく設定されているか確認
