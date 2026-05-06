# Docker メンテナンス作業書

## 1. 前提

この作業書は、Lattice Index を Ubuntu Server 上で Docker Compose により運用する場合のメンテナンス手順をまとめたものです。

想定環境:

- OS: Ubuntu Server 22.04 LTS 以降
- 実行ユーザー: `lattice` などの専用一般ユーザー
- 配置先: `/opt/lattice-index`
- 起動方式: Docker Compose
- Backend: FastAPI
- Frontend: SvelteKit
- DB: SQLite
- DB 保存先: `backend/data/lattice_index.sqlite3`

## 2. 基本コマンド

作業前にアプリケーションディレクトリへ移動します。

```bash
cd /opt/lattice-index
```

起動:

```bash
docker compose up -d
```

停止:

```bash
docker compose down
```

再起動:

```bash
docker compose restart
```

状態確認:

```bash
docker compose ps
```

ログ確認:

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend
```

## 3. 更新作業

通常の更新手順:

```bash
cd /opt/lattice-index
git pull
docker compose build
docker compose up -d
docker compose ps
```

更新後の疎通確認:

```bash
curl -f http://localhost:8000/api/locations
curl -f http://localhost:5173/
```

外部公開している場合は、Cloudflare Tunnel / Cloudflare Access 経由でもブラウザから確認します。

## 4. バックアップ

SQLite DB は `backend/data/lattice_index.sqlite3` に保存されます。更新作業や OS メンテナンス前には必ずバックアップします。

停止してバックアップする場合:

```bash
cd /opt/lattice-index
docker compose down
mkdir -p backups
cp backend/data/lattice_index.sqlite3 "backups/lattice_index_$(date +%Y%m%d_%H%M%S).sqlite3"
docker compose up -d
```

アプリ API からバックアップを作成する場合:

```bash
curl -X POST -o "lattice_index_backup_$(date +%Y%m%d_%H%M%S).sqlite3" http://localhost:8000/api/backup
```

CSV / JSON エクスポート:

```bash
curl -o "lattice_index_$(date +%Y%m%d_%H%M%S).csv" http://localhost:8000/api/export/csv
curl -o "lattice_index_$(date +%Y%m%d_%H%M%S).json" http://localhost:8000/api/export/json
```

## 5. リストア

DB を復元する場合は、必ず停止してから SQLite ファイルを差し替えます。

```bash
cd /opt/lattice-index
docker compose down
cp backups/lattice_index_YYYYMMDD_HHMMSS.sqlite3 backend/data/lattice_index.sqlite3
docker compose up -d
docker compose ps
```

復元後、一覧と検索が動作することを確認します。

```bash
curl -f http://localhost:8000/api/copies
curl -f "http://localhost:8000/api/search?q=test"
```

## 6. ディスク容量確認

Docker とバックアップで容量を使いすぎていないか確認します。

```bash
df -h
du -sh /opt/lattice-index
docker system df
```

不要な未使用イメージを削除する場合:

```bash
docker image prune
```

未使用コンテナ、ネットワーク、イメージをまとめて削除する場合:

```bash
docker system prune
```

注意: `docker system prune -a` は未使用イメージを広範囲に削除します。再ビルド時間が増えるため、必要な場合のみ実行します。

## 7. ログ肥大化対策

Docker ログが肥大化している場合は、`docker-compose.yml` にログローテーション設定を追加します。

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

追加後:

```bash
docker compose down
docker compose up -d
```

## 8. Ubuntu Server の定期メンテナンス

パッケージ更新:

```bash
sudo apt update
sudo apt upgrade
```

再起動が必要か確認:

```bash
test -f /var/run/reboot-required && cat /var/run/reboot-required
```

再起動前には DB バックアップを取得します。

```bash
cd /opt/lattice-index
mkdir -p backups
cp backend/data/lattice_index.sqlite3 "backups/lattice_index_before_reboot_$(date +%Y%m%d_%H%M%S).sqlite3"
sudo reboot
```

## 9. 障害時の確認順

1. コンテナ状態を確認する。

```bash
docker compose ps
```

2. Backend のログを確認する。

```bash
docker compose logs --tail=200 backend
```

3. Frontend のログを確認する。

```bash
docker compose logs --tail=200 frontend
```

4. DB ファイルの存在と権限を確認する。

```bash
ls -l backend/data
```

5. ローカル疎通を確認する。

```bash
curl -v http://localhost:8000/api/locations
curl -v http://localhost:5173/
```

## 10. 注意事項

- `backend/data/` は永続データの保存先です。削除すると蔵書データが失われます。
- `docker compose down -v` はボリュームを削除する可能性があるため、通常運用では使用しません。
- 更新、復元、OS 再起動の前には SQLite DB をバックアップします。
- Cloudflare Tunnel / Cloudflare Access を使う場合、アプリ側ではなく Cloudflare 側の認証設定も合わせて確認します。
