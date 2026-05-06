# Lattice Index

個人蔵書を ISBN で登録し、copies 単位で検索・所在地確認するセルフホスト型 Web/PWA アプリです。

## 起動

```powershell
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- OpenAPI: http://localhost:8000/docs

ローカル実行する場合:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

別ターミナル:

```powershell
cd frontend
npm install
npm run dev
```

## 実装済み MVP 機能

- ISBN-10 / ISBN-13 正規化とチェックディジット検証
- openBD 優先、Google Books fallback の書誌取得
- 登録確認フォームと手入力登録
- 同一 ISBN 登録時の警告と copies 追加
- copies 単位の一覧、詳細、関連コピー表示
- タイトル、著者、ISBN、所在地、メモの検索
- 所有状態を `disposed` / `lost` / `sold` に変更
- 所在地の追加と非表示
- CSV / JSON エクスポート
- SQLite バックアップ作成
- Web App Manifest と Service Worker による PWA 基本対応

