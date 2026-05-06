<script lang="ts">
  import {
    Archive,
    BookOpen,
    Camera,
    Check,
    Database,
    Download,
    FileJson,
    Home,
    MapPin,
    PackagePlus,
    Plus,
    Search,
    Settings,
    Trash2,
    Upload,
    X
  } from 'lucide-svelte';
  import { BarcodeFormat, DecodeHintType } from '@zxing/library';
  import { BrowserMultiFormatReader, type IScannerControls } from '@zxing/browser';
  import { onDestroy, onMount } from 'svelte';
  import { API_BASE, api, type CopyRow, type Location, type LookupResult } from '$lib/api';

  type View = 'home' | 'add' | 'settings';

  const emptyForm = {
    title: '',
    author: '',
    series_name: '',
    volume_number: '',
    publisher: '',
    label: '',
    category: '',
    location_id: 0,
    location_detail: '',
    memo: ''
  };

  let view: View = 'home';
  let copies: CopyRow[] = [];
  let locations: Location[] = [];
  let query = '';
  let locationFilter = '';
  let loading = false;
  let message = '';
  let selected: CopyRow | null = null;

  let isbn = '';
  let lookup: LookupResult | null = null;
  let duplicate: { existing_book_id?: number; existing_copies?: CopyRow[]; message?: string } | null = null;
  let form = { ...emptyForm };
  let newLocation = '';
  let csvFile: File | null = null;

  let videoElement: HTMLVideoElement;
  let scannerControls: IScannerControls | null = null;
  let cameraActive = false;
  let cameraMessage = '';
  let cameraSupported = false;
  let cameraSecureContext = false;
  let scanLocked = false;

  $: activeLocations = locations.filter((location) => location.is_active);

  async function load() {
    loading = true;
    message = '';
    try {
      [locations, copies] = await Promise.all([api.locations(), api.copies()]);
      if (!form.location_id && activeLocations[0]) form.location_id = activeLocations[0].id;
    } catch (error) {
      message = error instanceof Error ? error.message : '読み込みに失敗しました。';
    } finally {
      loading = false;
    }
  }

  async function runSearch() {
    loading = true;
    try {
      copies = query.trim() || locationFilter ? await api.search(query, locationFilter) : await api.copies();
    } catch (error) {
      message = error instanceof Error ? error.message : '検索に失敗しました。';
    } finally {
      loading = false;
    }
  }

  async function lookupIsbn() {
    if (!isbn.trim()) {
      message = 'ISBNを入力してください。';
      return;
    }
    loading = true;
    duplicate = null;
    message = '';
    try {
      lookup = await api.lookup(isbn);
      form = {
        ...form,
        title: lookup.title ?? '',
        author: lookup.author ?? '',
        publisher: lookup.publisher ?? '',
        category: lookup.category ?? ''
      };
      if (!lookup.title) message = '書誌情報が見つかりませんでした。手入力で登録できます。';
    } catch (error) {
      message = error instanceof Error ? error.message : 'ISBN検索に失敗しました。';
    } finally {
      loading = false;
    }
  }

  function normalizeScannedIsbn(value: string) {
    return value.replace(/[^0-9Xx]/g, '');
  }

  function createScanner() {
    const hints = new Map<DecodeHintType, unknown>();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.EAN_13, BarcodeFormat.EAN_8, BarcodeFormat.UPC_A]);
    hints.set(DecodeHintType.TRY_HARDER, true);
    return new BrowserMultiFormatReader(hints, {
      delayBetweenScanAttempts: 120,
      delayBetweenScanSuccess: 400
    });
  }

  async function startCameraScan() {
    if (!cameraSupported) {
      cameraMessage = 'このブラウザではカメラ読み取りを利用できません。';
      return;
    }
    if (!cameraSecureContext) {
      cameraMessage = 'カメラを使うにはHTTPS、またはlocalhostで開いてください。携帯から使う場合はHTTPS配信が必要です。';
      return;
    }

    await stopCameraScan();
    cameraMessage = '本の裏表紙のバーコードを枠内に合わせてください。';
    cameraActive = true;
    scanLocked = false;
    try {
      scannerControls = await createScanner().decodeFromVideoDevice(undefined, videoElement, async (result) => {
        if (!result || scanLocked) return;
        const scanned = normalizeScannedIsbn(result.getText());
        if (!scanned) return;
        scanLocked = true;
        isbn = scanned;
        cameraMessage = `読み取りました: ${scanned}`;
        await stopCameraScan();
        await lookupIsbn();
      });
    } catch (error) {
      cameraActive = false;
      cameraMessage = error instanceof Error ? error.message : 'カメラの起動に失敗しました。';
    }
  }

  async function stopCameraScan() {
    scannerControls?.stop();
    scannerControls = null;
    cameraActive = false;
    if (videoElement) videoElement.srcObject = null;
  }

  function buildBookPayload(duplicateAction = false) {
    return {
      isbn13: lookup?.isbn13 || isbn || null,
      title: form.title,
      author: form.author || null,
      series_name: form.series_name || null,
      volume_number: form.volume_number || null,
      publisher: form.publisher || null,
      label: form.label || null,
      category: form.category || null,
      published_date: lookup?.published_date ?? null,
      page_count: lookup?.page_count ?? null,
      description: lookup?.description ?? null,
      cover_url: lookup?.cover_url ?? null,
      metadata_source: lookup?.source ?? 'manual',
      metadata_raw_json: lookup?.raw ?? null,
      duplicate_action: duplicateAction ? 'add_copy' : null,
      copy: {
        location_id: form.location_id || null,
        location_detail: form.location_detail || null,
        memo: form.memo || null,
        condition: 'unknown'
      }
    };
  }

  async function registerBook(duplicateAction = false) {
    if (!form.title.trim()) {
      message = 'タイトルは必須です。';
      return;
    }
    loading = true;
    try {
      const result = await api.createBook(buildBookPayload(duplicateAction));
      if (result.status === 'duplicate') {
        duplicate = result;
        message = result.message ?? '重複しています。';
        return;
      }
      message = '登録しました。';
      duplicate = null;
      lookup = null;
      isbn = '';
      form = { ...emptyForm, location_id: form.location_id };
      view = 'home';
      await load();
    } catch (error) {
      message = error instanceof Error ? error.message : '登録に失敗しました。';
    } finally {
      loading = false;
    }
  }

  async function openDetail(copy: CopyRow) {
    selected = await api.copy(copy.copy_id);
  }

  async function setStatus(copy: CopyRow, ownership_status: CopyRow['ownership_status']) {
    selected = await api.updateCopy(copy.copy_id, { ownership_status });
    await runSearch();
  }

  async function setSelectedStatus(ownership_status: CopyRow['ownership_status']) {
    if (!selected) return;
    await setStatus(selected, ownership_status);
  }

  async function addLocation() {
    if (!newLocation.trim()) return;
    await api.createLocation(newLocation.trim());
    newLocation = '';
    locations = await api.locations();
  }

  async function toggleLocation(location: Location) {
    await api.updateLocation(location.id, { is_active: location.is_active ? 0 : 1 });
    locations = await api.locations();
  }

  async function importCsv() {
    if (!csvFile) {
      message = 'CSVファイルを選択してください。';
      return;
    }
    loading = true;
    message = '';
    try {
      const result = await api.importCsv(csvFile);
      message = `CSV取り込み完了: ${result.imported}件登録、${result.skipped}件スキップ`;
      csvFile = null;
      await load();
    } catch (error) {
      message = error instanceof Error ? error.message : 'CSV取り込みに失敗しました。';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    cameraSupported = Boolean(navigator.mediaDevices?.getUserMedia);
    cameraSecureContext = window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname);
    load();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  });

  onDestroy(() => {
    void stopCameraScan();
  });
</script>

<svelte:head>
  <title>Lattice Index</title>
  <meta name="description" content="個人蔵書をISBNで登録、検索、所在地管理できるPWA" />
</svelte:head>

<main class="shell">
  <header class="topbar">
    <button class:active={view === 'home'} on:click={() => (view = 'home')} aria-label="ホーム"><Home size={20} /></button>
    <strong>Lattice Index</strong>
    <button class:active={view === 'settings'} on:click={() => (view = 'settings')} aria-label="設定"><Settings size={20} /></button>
  </header>

  {#if message}
    <div class="notice">{message}</div>
  {/if}

  {#if view === 'home'}
    <section class="toolbar">
      <div class="searchbox">
        <Search size={18} />
        <input bind:value={query} on:input={runSearch} placeholder="タイトル、著者、ISBN、所在地..." />
      </div>
      <div class="chips">
        <button class:active={locationFilter === ''} on:click={() => { locationFilter = ''; runSearch(); }}>すべて</button>
        {#each activeLocations as location}
          <button class:active={locationFilter === location.name} on:click={() => { locationFilter = location.name; runSearch(); }}>{location.name}</button>
        {/each}
      </div>
    </section>

    <section class="summary">
      <div><span>{copies.length}</span><small>表示中</small></div>
      <div><span>{copies.filter((copy) => !copy.location_detail).length}</span><small>未整理</small></div>
      <div><span>{activeLocations.length}</span><small>所在地</small></div>
    </section>

    <section class="list" aria-busy={loading}>
      {#each copies as copy}
        <button class="book-row" on:click={() => openDetail(copy)}>
          <div class="cover">
            {#if copy.cover_url}<img src={copy.cover_url} alt="" />{:else}<BookOpen size={20} />{/if}
          </div>
          <div class="book-main">
            <strong>{copy.title}</strong>
            <span>{copy.author || '著者未設定'}</span>
            <small>{copy.series_name || ''}{copy.volume_number ? ` ${copy.volume_number}` : ''}</small>
          </div>
          <div class="location-pill">{copy.location_name || '未設定'}</div>
        </button>
      {:else}
        <div class="empty">該当する蔵書がありません。</div>
      {/each}
    </section>

    <button class="fab" on:click={() => (view = 'add')} aria-label="追加"><Plus size={26} /></button>
  {:else if view === 'add'}
    <section class="panel">
      <div class="section-title">
        <PackagePlus size={20} />
        <h1>ISBN登録</h1>
      </div>
      <div class="isbn-row">
        <input bind:value={isbn} placeholder="978..." inputmode="numeric" />
        <button on:click={lookupIsbn} disabled={loading}>取得</button>
      </div>
      <div class="camera-card">
        <div class="camera-actions">
          <button on:click={startCameraScan} disabled={loading || cameraActive}><Camera size={18} />カメラで読む</button>
          {#if cameraActive}
            <button class="secondary" on:click={stopCameraScan}><X size={18} />停止</button>
          {/if}
        </div>
        <div class:active={cameraActive} class="camera-preview">
          <video bind:this={videoElement} autoplay muted playsinline></video>
          {#if !cameraActive}
            <div class="camera-placeholder"><Camera size={24} /></div>
          {/if}
        </div>
        <p class="hint">{cameraMessage || '携帯ではホーム画面に追加して、HTTPSで開くとカメラ読み取りを利用できます。'}</p>
      </div>
    </section>

    <section class="panel form-grid">
      {#if lookup?.cover_url}
        <img class="preview-cover" src={lookup.cover_url} alt="" />
      {/if}
      <label>タイトル<input bind:value={form.title} /></label>
      <label>著者<input bind:value={form.author} /></label>
      <label>シリーズ<input bind:value={form.series_name} /></label>
      <label>巻数<input bind:value={form.volume_number} /></label>
      <label>出版社<input bind:value={form.publisher} /></label>
      <label>レーベル<input bind:value={form.label} /></label>
      <label>カテゴリ<input bind:value={form.category} /></label>
      <label>所在地
        <select bind:value={form.location_id}>
          {#each activeLocations as location}
            <option value={location.id}>{location.name}</option>
          {/each}
        </select>
      </label>
      <label>詳細場所<input bind:value={form.location_detail} placeholder="本棚 2段目" /></label>
      <label>メモ<textarea bind:value={form.memo} rows="3"></textarea></label>
      {#if duplicate}
        <div class="duplicate">
          <strong>{duplicate.message}</strong>
          {#each duplicate.existing_copies ?? [] as existing}
            <span>{existing.location_name || '未設定'} {existing.location_detail || ''}</span>
          {/each}
          <button on:click={() => registerBook(true)}><Check size={18} />別冊として追加</button>
        </div>
      {/if}
      <button class="primary" on:click={() => registerBook(false)} disabled={loading}>登録する</button>
    </section>
  {:else}
    <section class="panel">
      <div class="section-title">
        <MapPin size={20} />
        <h1>所在地</h1>
      </div>
      <div class="isbn-row">
        <input bind:value={newLocation} placeholder="所在地を追加" />
        <button on:click={addLocation}>追加</button>
      </div>
      <div class="location-list">
        {#each locations as location}
          <button on:click={() => toggleLocation(location)}>
            <span>{location.name}</span>
            <small>{location.is_active ? '表示中' : '非表示'}</small>
          </button>
        {/each}
      </div>
    </section>

    <section class="panel actions">
      <a href={`${API_BASE}/api/export/csv`}><Download size={18} />CSVエクスポート</a>
      <a href={`${API_BASE}/api/export/json`}><FileJson size={18} />JSONエクスポート</a>
      <a href={`${API_BASE}/api/backup`} data-method="post" on:click|preventDefault={async () => { await fetch(`${API_BASE}/api/backup`, { method: 'POST' }); message = 'SQLiteバックアップを作成しました。'; }}><Database size={18} />SQLiteバックアップ</a>
    </section>

    <section class="panel">
      <div class="section-title">
        <Upload size={20} />
        <h1>CSV取り込み</h1>
      </div>
      <div class="import-row">
        <input
          type="file"
          accept=".csv,text/csv"
          on:change={(event) => {
            csvFile = event.currentTarget.files?.[0] ?? null;
          }}
        />
        <button on:click={importCsv} disabled={loading || !csvFile}><Upload size={18} />取り込み</button>
      </div>
      <p class="hint">CSVエクスポートと同じ列形式を取り込めます。UTF-8 / Shift_JIS に対応しています。</p>
    </section>
  {/if}
</main>

{#if selected}
  <button class="modal-backdrop" on:click={() => (selected = null)} aria-label="詳細を閉じる"></button>
  <aside class="detail">
    <button class="close" on:click={() => (selected = null)} aria-label="閉じる"><X size={20} /></button>
    <div class="detail-head">
      <div class="cover large">{#if selected.cover_url}<img src={selected.cover_url} alt="" />{:else}<BookOpen size={28} />{/if}</div>
      <div>
        <h2>{selected.title}</h2>
        <p>{selected.author || '著者未設定'}</p>
        <small>{selected.isbn13}</small>
      </div>
    </div>
    <dl>
      <dt>所在地</dt><dd>{selected.location_name || '未設定'} {selected.location_detail || ''}</dd>
      <dt>シリーズ</dt><dd>{selected.series_name || '-'} {selected.volume_number || ''}</dd>
      <dt>出版社</dt><dd>{selected.publisher || '-'}</dd>
      <dt>所有状態</dt><dd>{selected.ownership_status}</dd>
      <dt>メモ</dt><dd>{selected.memo || '-'}</dd>
    </dl>
    {#if selected.related_copies?.length}
      <h3>同じ本の別コピー</h3>
      {#each selected.related_copies as related}
        <div class="related">{related.location_name || '未設定'} {related.location_detail || ''}</div>
      {/each}
    {/if}
    <div class="status-actions">
      <button on:click={() => setSelectedStatus('disposed')}><Trash2 size={16} />処分済み</button>
      <button on:click={() => setSelectedStatus('lost')}><Archive size={16} />紛失</button>
      <button on:click={() => setSelectedStatus('sold')}><Archive size={16} />売却</button>
    </div>
  </aside>
{/if}
