<script lang="ts">
  import {
    Archive,
    BookOpen,
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
    X
  } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { API_BASE, api, type CopyRow, type Location, type LookupResult } from '$lib/api';

  type View = 'home' | 'add' | 'settings';

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
  let form = {
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
  let newLocation = '';

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
      form = { ...form, title: '', author: '', series_name: '', volume_number: '', publisher: '', label: '', category: '', location_detail: '', memo: '' };
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

  onMount(() => {
    load();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  });
</script>

<svelte:head>
  <title>Lattice Index</title>
  <meta name="description" content="個人蔵書を素早く登録・検索するセルフホスト型アプリ" />
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
          <div class="location-pill">{copy.location_name || '不明'}</div>
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
      <p class="hint">カメラ非対応でも登録できるよう、MVPでは手入力を残しています。</p>
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
      <label>詳細場所<input bind:value={form.location_detail} placeholder="本棚A 2段目" /></label>
      <label>メモ<textarea bind:value={form.memo} rows="3"></textarea></label>
      {#if duplicate}
        <div class="duplicate">
          <strong>{duplicate.message}</strong>
          {#each duplicate.existing_copies ?? [] as existing}
            <span>{existing.location_name || '不明'} {existing.location_detail || ''}</span>
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
      <dt>所在地</dt><dd>{selected.location_name || '不明'} {selected.location_detail || ''}</dd>
      <dt>シリーズ</dt><dd>{selected.series_name || '-'} {selected.volume_number || ''}</dd>
      <dt>出版社</dt><dd>{selected.publisher || '-'}</dd>
      <dt>所有状態</dt><dd>{selected.ownership_status}</dd>
      <dt>メモ</dt><dd>{selected.memo || '-'}</dd>
    </dl>
    {#if selected.related_copies?.length}
      <h3>同じ本の別コピー</h3>
      {#each selected.related_copies as related}
        <div class="related">{related.location_name || '不明'} {related.location_detail || ''}</div>
      {/each}
    {/if}
    <div class="status-actions">
      <button on:click={() => setSelectedStatus('disposed')}><Trash2 size={16} />処分済み</button>
      <button on:click={() => setSelectedStatus('lost')}><Archive size={16} />紛失</button>
      <button on:click={() => setSelectedStatus('sold')}><Archive size={16} />売却</button>
    </div>
  </aside>
{/if}
