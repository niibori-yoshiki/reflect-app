# SEAOS Workspace セットアップファイル

このブランチには `seaos-workspace` リポジトリ用のファイルが含まれています。

## 新しいリポジトリへの移行手順

1. GitHubで `seaos-workspace`（Private）リポジトリを作成
2. 以下のファイルを新リポジトリに移動：
   - `docs/` → Windows環境セットアップ手順、Claude Code活用ガイド
   - `templates/` → 環境変数テンプレート
   - `.gitignore`
3. `/home/user/seaos-workspace/README.md` の内容を新リポジトリの `README.md` として使用

## ファイル一覧

| ファイル | 内容 |
|---|---|
| `docs/windows-setup.md` | Windows社用PCの開発環境構築手順 |
| `docs/claude-code-guide.md` | Claude Code導入・活用ガイド |
| `templates/.env.example` | 環境変数テンプレート |
| `.gitignore` | Git除外設定 |
