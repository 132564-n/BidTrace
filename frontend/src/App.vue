<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const documents = ref([])
const selectedTenderId = ref('')
const selectedBidId = ref('')
const sourceMode = ref('demo')
const review = ref(null)
const modelAvailable = ref(false)
const selectedFindingIndex = ref(0)
const tenderContext = ref('')
const bidContext = ref('')
const evaluation = ref(null)
const busy = ref('')
const error = ref('')
const notice = ref('')

const tenders = computed(() => documents.value.filter((item) => item.kind === 'tender'))
const bids = computed(() => documents.value.filter((item) => item.kind === 'bid'))
const findings = computed(() => review.value?.findings || [])
const selectedFinding = computed(() => findings.value[selectedFindingIndex.value] || null)
const stage = computed(() => review.value?.findings ? 3 : review.value ? 2 : 1)
const counts = computed(() => findings.value.reduce((total, finding) => {
  total[finding.status] = (total[finding.status] || 0) + 1
  return total
}, {}))

watch([selectedTenderId, selectedBidId, sourceMode], () => {
  review.value = null
  evaluation.value = null
  selectedFindingIndex.value = 0
  tenderContext.value = ''
  bidContext.value = ''
})

async function api(path, options = {}) {
  const response = await fetch(path, options)
  const type = response.headers.get('content-type') || ''
  const result = type.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(result?.detail || `请求失败（${response.status}）`)
  return result
}

function jsonOptions(body) {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

async function refreshDocuments() {
  documents.value = await api('/api/documents')
  if (!selectedTenderId.value) selectedTenderId.value = tenders.value[0]?.id || ''
  if (!selectedBidId.value) selectedBidId.value = bids.value[0]?.id || ''
}

async function loadDemo() {
  busy.value = 'demo'
  error.value = ''
  try {
    const demo = await api('/api/demo/load', { method: 'POST' })
    await refreshDocuments()
    selectedTenderId.value = demo.tender.id
    selectedBidId.value = demo.flawed.id
    sourceMode.value = 'demo'
    review.value = null
    evaluation.value = null
    notice.value = '已载入公开招标文件和两份模拟投标文件。'
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = ''
  }
}

async function uploadFile(event, kind) {
  const file = event.target.files?.[0]
  if (!file) return
  busy.value = 'upload'
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    const document = await api('/api/documents', { method: 'POST', body: form })
    await refreshDocuments()
    if (kind === 'tender') selectedTenderId.value = document.id
    else selectedBidId.value = document.id
    review.value = null
    evaluation.value = null
    notice.value = `${file.name} 已上传，共 ${document.page_count} 页。`
  } catch (exception) {
    error.value = exception.message
  } finally {
    event.target.value = ''
    busy.value = ''
  }
}

async function createReview() {
  if (!selectedTenderId.value || !selectedBidId.value) {
    error.value = '请先选择一份招标文件和一份投标文件。'
    return
  }
  busy.value = 'create'
  error.value = ''
  notice.value = ''
  try {
    review.value = await api('/api/reviews', jsonOptions({
      tender_id: selectedTenderId.value,
      bid_id: selectedBidId.value,
      source_mode: sourceMode.value,
    }))
    evaluation.value = null
    notice.value = `${sourceMode.value === 'demo' ? '已载入' : '已提取'} ${review.value.checks.length} 条检查项。请核对原文、页码和门槛后再审核。`
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = ''
  }
}

async function confirmAndRun() {
  if (!review.value) return
  busy.value = 'run'
  error.value = ''
  notice.value = ''
  try {
    review.value = await api(`/api/reviews/${review.value.id}/checks`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(review.value.checks),
    })
    review.value = await api(`/api/reviews/${review.value.id}/run`, { method: 'POST' })
    selectedFindingIndex.value = 0
    await showEvidence(0)
    if (review.value.source_mode === 'demo') {
      evaluation.value = await api(`/api/reviews/${review.value.id}/evaluation`)
    }
    notice.value = '审核已完成。点击任意检查项查看双方原文。'
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = ''
  }
}

async function showEvidence(index) {
  selectedFindingIndex.value = index
  const finding = findings.value[index]
  if (!finding || !review.value) return
  const tender = await api(`/api/documents/${review.value.tender_id}/pages/${finding.source_page}`)
  tenderContext.value = tender.text
  bidContext.value = finding.bid_page
    ? (await api(`/api/documents/${review.value.bid_id}/pages/${finding.bid_page}`)).text
    : ''
}

function documentUrl(kind, page) {
  const id = kind === 'tender' ? review.value?.tender_id : review.value?.bid_id
  return id ? `/api/documents/${id}/file#page=${page || 1}` : '#'
}

function statusClass(status) {
  return {
    '满足': 'ok', '明确冲突': 'conflict', '未找到证据': 'missing', '需人工复核': 'review',
  }[status] || 'review'
}

onMounted(async () => {
  try {
    const health = await api('/api/health')
    modelAvailable.value = health.model_available
    await refreshDocuments()
  } catch (exception) {
    error.value = '无法连接审核服务。请先启动后端，再刷新页面。'
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark" aria-hidden="true">┃</span><span>标尺</span><small>投标文件自查</small></div>
      <div class="topbar-right"><span class="model-dot" :class="{ active: modelAvailable }"></span>{{ modelAvailable ? '模型已连接' : '模型未连接 · 技术项需人工复核' }}</div>
    </header>

    <main class="workspace">
      <aside class="setup-panel">
        <div class="eyebrow">审核工作台</div>
        <h1>逐条核对，<br>再提交。</h1>
        <p class="intro">把招标要求与投标响应放在同一张证据桌上，先看原文，再看结论。</p>

        <div class="stages" aria-label="审核步骤">
          <div :class="['stage', { current: stage === 1, done: stage > 1 }]"><b>1</b><span>选择文件</span></div>
          <div :class="['stage', { current: stage === 2, done: stage > 2 }]"><b>2</b><span>确认检查项</span></div>
          <div :class="['stage', { current: stage === 3 }]"><b>3</b><span>核对结果</span></div>
        </div>

        <section class="setup-section">
          <div class="section-heading"><h2>文件</h2><button class="text-button" :disabled="!!busy" @click="loadDemo">载入演示样本</button></div>
          <label class="field-label" for="tender">招标文件</label>
          <select id="tender" v-model="selectedTenderId" :disabled="!!busy">
            <option value="">请选择</option><option v-for="item in tenders" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <label class="upload-link">+ 上传招标 PDF<input type="file" accept="application/pdf,.pdf" :disabled="!!busy" @change="uploadFile($event, 'tender')"></label>
          <label class="field-label" for="bid">投标文件</label>
          <select id="bid" v-model="selectedBidId" :disabled="!!busy">
            <option value="">请选择</option><option v-for="item in bids" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
          <label class="upload-link">+ 上传投标 PDF<input type="file" accept="application/pdf,.pdf" :disabled="!!busy" @change="uploadFile($event, 'bid')"></label>
        </section>

        <section class="setup-section">
          <h2>检查项来源</h2>
          <label class="radio-row"><input v-model="sourceMode" type="radio" value="demo"> 使用已标注的演示检查项</label>
          <label class="radio-row"><input v-model="sourceMode" type="radio" value="model" :disabled="!modelAvailable"> 从当前招标文件提取</label>
          <p class="helper">模型提出检查项后，仍需你确认原文、页码和数字门槛。</p>
          <button class="primary-button" :disabled="!!busy || !selectedTenderId || !selectedBidId" @click="createReview">
            {{ busy === 'create' ? '正在生成…' : '生成检查项' }}
          </button>
        </section>
        <p class="privacy-note">支持可复制文字的 PDF。未找到证据表示需要翻阅原件，不等于确认缺失。使用模型时，招标文字与候选投标片段会发送至 DeepSeek。</p>
      </aside>

      <section class="main-panel">
        <div class="feedback" v-if="error || notice" :class="error ? 'feedback-error' : 'feedback-note'" role="status">{{ error || notice }}</div>
        <div v-if="!review" class="empty-state">
          <div class="empty-icon" aria-hidden="true">≡</div>
          <div class="eyebrow">待开始</div>
          <h2>从两份文件开始</h2>
          <p>选择招标文件和投标文件，生成一份待确认的检查清单。你可以先载入演示样本体验完整流程。</p>
        </div>

        <template v-else-if="!review.findings">
          <div class="panel-heading"><div><div class="eyebrow">第二步 · 人工确认</div><h2>检查清单</h2><p>核对每条招标原文和页码；可关闭本次不需要的检查。</p></div><span class="count-mark">{{ review.checks.length }} 项</span></div>
          <div class="check-list">
            <article v-for="check in review.checks" :key="check.id" class="check-card">
              <div class="check-top"><span class="rule-id">{{ check.id }}</span><span class="category">{{ check.category === 'numeric' ? '数字条件' : check.category === 'semantic' ? '技术响应' : '文件存在性' }}</span><label class="switch"><input v-model="check.enabled" type="checkbox"><span>纳入审核</span></label></div>
              <label class="edit-label">检查内容<input v-model="check.name" type="text"></label>
              <div v-if="check.category === 'numeric'" class="numeric-edit"><label class="edit-label">比较方式<input v-model="check.operator" type="text"></label><label class="edit-label">门槛<input v-model="check.threshold" type="text"></label><label class="edit-label">单位<input v-model="check.unit" type="text"></label></div>
              <div v-if="check.category === 'document_presence'" class="numeric-edit"><label class="edit-label">查找名称<input v-model="check.target" type="text"></label></div>
              <div class="source-line"><span>招标文件 · PDF 第 {{ check.source_page }} 页</span><blockquote>{{ check.source_quotes.join('；') }}</blockquote></div>
            </article>
          </div>
          <div class="sticky-actions"><span>确认后才会执行数字比较与响应判断</span><button class="primary-button" :disabled="!!busy" @click="confirmAndRun">{{ busy === 'run' ? '正在审核…' : '确认并开始审核' }}</button></div>
        </template>

        <template v-else>
          <div class="panel-heading results-heading"><div><div class="eyebrow">第三步 · 逐项核对</div><h2>审核结果</h2><p>结论与证据并排展示。点击检查项查看完整页文本。</p></div><span class="count-mark">{{ findings.length }} 项</span></div>
          <div class="summary-strip"><span><b>{{ counts['明确冲突'] || 0 }}</b>明确冲突</span><span><b>{{ counts['未找到证据'] || 0 }}</b>未找到证据</span><span><b>{{ counts['需人工复核'] || 0 }}</b>需人工复核</span><span><b>{{ counts['满足'] || 0 }}</b>满足</span></div>
          <div v-if="evaluation" class="evaluation">演示样本核对：{{ evaluation.correct }} / {{ evaluation.total }} 项与人工标注一致。<small>{{ evaluation.note }}</small></div>
          <div class="report-actions"><a :href="`/api/reviews/${review.id}/report.html`" target="_blank" rel="noopener">打开可打印报告 ↗</a><a :href="`/api/reviews/${review.id}/report.json`" download="标尺审核结果.json">下载结构化结果 ↓</a></div>
          <div class="finding-list">
            <button v-for="(finding, index) in findings" :key="finding.rule_id" :class="['finding-row', statusClass(finding.status), { selected: selectedFindingIndex === index }]" @click="showEvidence(index)">
              <span class="finding-id">{{ finding.rule_id }}</span><span class="finding-name">{{ finding.name }}</span><span class="status-tag">{{ finding.status }}</span><span class="row-arrow" aria-hidden="true">›</span>
            </button>
          </div>
        </template>
      </section>

      <aside class="evidence-panel">
        <template v-if="selectedFinding">
          <div class="eyebrow">原文证据</div><h2>{{ selectedFinding.name }}</h2><span :class="['large-status', statusClass(selectedFinding.status)]">{{ selectedFinding.status }}</span>
          <p class="reason">{{ selectedFinding.reason }}</p>
          <div class="evidence-block"><div class="evidence-head"><span>招标要求 · PDF 第 {{ selectedFinding.source_page }} 页</span><a :href="documentUrl('tender', selectedFinding.source_page)" target="_blank" rel="noopener">打开原件 ↗</a></div><blockquote>{{ selectedFinding.source_quotes.join('；') }}</blockquote><details><summary>查看该页文字</summary><pre>{{ tenderContext }}</pre></details></div>
          <div class="evidence-block bid-block"><div class="evidence-head"><span>{{ selectedFinding.status === '需人工复核' ? '投标候选原文' : '投标响应' }} · {{ selectedFinding.bid_page ? `PDF 第 ${selectedFinding.bid_page} 页` : '待定位' }}</span><a v-if="selectedFinding.bid_page" :href="documentUrl('bid', selectedFinding.bid_page)" target="_blank" rel="noopener">打开原件 ↗</a></div><blockquote>{{ selectedFinding.bid_quote || '未找到可引用的投标原文。请人工翻阅完整文件。' }}</blockquote><details v-if="selectedFinding.bid_page"><summary>查看该页文字</summary><pre>{{ bidContext }}</pre></details></div>
          <div v-if="selectedFinding.candidates?.length" class="candidate-note">已检索 {{ selectedFinding.candidates.length }} 段候选文字；结论仅引用上方可核对的原文。</div>
        </template>
        <div v-else class="evidence-empty"><span aria-hidden="true">⇄</span><h2>原文会在这里对照</h2><p>审核完成后，选择一条结果即可查看招标要求和投标响应的页码与原文。</p></div>
      </aside>
    </main>
  </div>
</template>
