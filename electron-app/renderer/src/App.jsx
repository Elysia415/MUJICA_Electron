import React, { useState, useEffect, useRef } from 'react';
import { api } from './api';
import { JobStatus } from './components/JobStatus';
import { MarkdownRenderer, slugify } from './components/MarkdownRenderer';
import { KnowledgeBaseView } from './components/KnowledgeBaseView';
import { SettingsView } from './components/SettingsView';
import { HistoryView } from './components/HistoryView';
import { PlanEditor } from './components/PlanEditor';
import { ReportView } from './components/ReportView';
import { useTheme } from './components/ThemeProvider';
import { Send, FileText, Database, PlusCircle, Settings, Play, BookOpen, Search, X, Sun, Moon, Download, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
  const [query, setQuery] = useState('');
  const [activeJobId, setActiveJobId] = useState(null);
  const [jobState, setJobState] = useState(null);
  const [view, setView] = useState('chat'); // chat, history, kb
  const [polling, setPolling] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const { theme, toggleTheme } = useTheme();

  // Split View State
  const [evidencePanelOpen, setEvidencePanelOpen] = useState(true);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [kbTargetPaperId, setKbTargetPaperId] = useState(null); // For navigating to KB

  // Configuration
  const [config, setConfig] = useState({
    model_name: '', // Removed hardcoded default
    api_key: '',
    base_url: '',
  });

  const pollInterval = useRef(null);

  // Initial Config Load
  const loadAppConfig = () => {
    api.getConfig().then(res => {
      console.log("[App] Config loaded:", res.data);
      setConfig(prev => ({ ...prev, ...res.data }));
    }).catch(err => {
      console.error("[App] Failed to load config:", err);
      // Retry once after 2s if failed (backoff)
      setTimeout(() => {
        api.getConfig().then(res => setConfig(prev => ({ ...prev, ...res.data }))).catch(console.error);
      }, 2000);
    });
  };

  useEffect(() => {
    loadAppConfig();
  }, []);

  // Polling Logic
  useEffect(() => {
    if (!polling || !activeJobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.getJob(activeJobId);
        setJobState(res.data);
        if (['done', 'error', 'cancelled'].includes(res.data.status)) {
          setPolling(false);
        }
      } catch (e) {
        console.error("Polling error", e);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [activeJobId, polling]);

  const handleStartPlan = async () => {
    if (!query.trim()) return;
    setView('chat');
    try {
      setJobState(null);
      const res = await api.startPlan(query, {
        model_name: config.MUJICA_DEFAULT_MODEL || 'deepseek-chat', // Default to deepseek-chat if config missing
        api_key: config.OPENAI_API_KEY,
        base_url: config.OPENAI_BASE_URL
      });
      setActiveJobId(res.data.job_id);
      setPolling(true);
    } catch (e) {
      alert("启动规划失败: " + e.message);
    }
  };

  const handleStartResearch = async () => {
    if (!jobState?.result?.plan) return;
    try {
      const res = await api.startResearch(jobState.result.plan, {
        model_name: config.MUJICA_DEFAULT_MODEL || 'gpt-4o',
        chat_api_key: config.OPENAI_API_KEY,
        chat_base_url: config.OPENAI_BASE_URL,
        embedding_model: config.MUJICA_EMBEDDING_MODEL || 'text-embedding-3-small',
        embedding_api_key: config.MUJICA_EMBEDDING_API_KEY || config.OPENAI_API_KEY,
        embedding_base_url: config.MUJICA_EMBEDDING_BASE_URL || config.OPENAI_BASE_URL
      });
      setActiveJobId(res.data.job_id);
      setPolling(true);
    } catch (e) {
      alert("启动调研失败: " + e.message);
    }
  };

  const loadHistoryItem = (data) => {
    // Restore state from history snapshot
    // Handles both new format (nested in job_result) and old format (flat)
    setQuery('');

    // Extract actual result object
    // New format: data.job_result
    // Old format: data itself
    const resultSource = data.job_result || data;

    const restoredJob = {
      status: 'done',
      type: 'research', // Assume research for now
      result: {
        plan: resultSource.plan || resultSource.pending_plan,
        research_notes: resultSource.research_notes,
        final_report: resultSource.final_report,
        verification_result: resultSource.verification_result,
        report_ref_ctx: resultSource.report_ref_ctx
      }
    };
    setJobState(restoredJob);
    setActiveJobId('RESTORED_HISTORY');
    setView('chat');
  };

  // Helper to extract evidence data
  const researchNotes = jobState?.result?.research_notes || [];
  const refContext = jobState?.result?.report_ref_ctx;
  const refItems = refContext?.ref_items || [];

  // Handle citation click from ReportView
  const handleCitationClick = (refId) => {
    // 1. Open Evidence Panel
    setEvidencePanelOpen(true);

    // 2. Find and select the item
    // refId e.g. "R1"
    const item = refItems.find(r => r.ref === refId);
    if (item) {
      setSelectedEvidence(item);
      // 3. Scroll to it
      setTimeout(() => {
        const el = document.getElementById(`evidence-${refId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          // Optional: Add highlight flash class
          el.classList.add('bg-accent/20');
          setTimeout(() => el.classList.remove('bg-accent/20'), 1500);
        }
      }, 100);
    } else {
      // Fallback: try to match by index if refId is just number (not expected logic but safety)
      console.warn(`Ref ${refId} not found in catalog.`);
    }
  };

  const handleJumpToPaper = (paperId, e) => {
    e?.stopPropagation();
    if (!paperId) return;
    setKbTargetPaperId(paperId);
    setView('kb');
  };

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden font-sans">
      {/* Sidebar */}
      <div className="w-16 md:w-64 bg-panel border-r border-border flex flex-col items-center md:items-stretch py-4 z-20 shadow-xl">
        <div className="flex items-center justify-center p-2 mb-8">
          <img src="./logo.png" alt="MUJICA" className="w-8 h-8 rounded-lg shadow-[0_0_15px_var(--accent)]" />
          <span className="hidden md:ml-3 font-bold text-xl tracking-widest text-accent-2">MUJICA</span>
        </div>

        <nav className="flex-1 flex flex-col gap-2 px-2">
          <NavBtn icon={<PlusCircle />} label="新建调研" active={view === 'chat' && !activeJobId} onClick={() => { setView('chat'); setActiveJobId(null); setJobState(null); setQuery(''); }} />
          <NavBtn icon={<BookOpen />} label="当前对话" active={view === 'chat' && !!activeJobId} onClick={() => setView('chat')} />
          <NavBtn icon={<FileText />} label="历史记录" active={view === 'history'} onClick={() => setView('history')} />
          <NavBtn icon={<Database />} label="知识库" active={view === 'kb'} onClick={() => setView('kb')} />
        </nav>

        <div className="px-2 mt-auto space-y-2">
          <button
            onClick={toggleTheme}
            className="flex items-center gap-3 p-3 rounded-lg w-full text-muted hover:bg-white/5 hover:text-text transition-all group"
          >
            <div className="transition-transform group-hover:scale-110">{theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}</div>
            <span className="hidden md:block font-medium whitespace-nowrap">{theme === 'dark' ? '亮色模式' : '暗色模式'}</span>
          </button>
          <NavBtn icon={<Settings />} label="设置" onClick={() => setShowSettings(true)} />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative bg-[url('/bg-noise.png')] h-full overflow-hidden">
        {/* Ambient Glows */}
        <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden z-0">
          <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-bg-glow-1 blur-[150px] opacity-40 rounded-full animate-pulse" />
          <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] bg-bg-glow-2 blur-[150px] opacity-30 rounded-full" />
        </div>

        {/* Dynamic Views */}
        <div className="z-10 flex-1 flex overflow-hidden">

          {/* View: Chat / Research */}
          {view === 'chat' && (
            <div className="flex-1 flex flex-row max-w-full h-full relative overflow-hidden">

              {/* Center Panel (Planner / Report) */}
              <div className="flex-1 flex flex-col h-full overflow-y-auto px-4 md:px-8 py-6 custom-scrollbar">

                {/* Welcome / Initial Input */}
                {!activeJobId ? (
                  <div className="flex flex-col items-center justify-center h-full max-w-3xl mx-auto w-full">
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center w-full">
                      <h1 className="text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-2 mb-3">
                        MUJICA · 睦鉴
                      </h1>
                      <p className="text-muted text-base mb-8">
                        输入一个主题，系统会自动规划 → 检索证据 → 写作 → 核查（全程可溯源）
                      </p>
                      <div className="bg-panel border border-border rounded-xl p-4 flex items-center gap-3 shadow-2xl w-full mb-10">
                        <input
                          type="text"
                          className="flex-1 bg-transparent border-none outline-none text-text px-4 py-3 placeholder-muted text-lg"
                          placeholder="今天想研究什么课题？"
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleStartPlan()}
                          autoFocus
                        />
                        <button onClick={handleStartPlan} className="p-3 bg-accent rounded-lg text-white hover:bg-accent-hover transition-colors">
                          <Send size={24} />
                        </button>
                      </div>

                      {/* Recommendation Examples */}
                      <div className="text-left">
                        <h3 className="text-base font-medium text-muted mb-4">推荐示例</h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                          {[
                            { title: 'DPO 研究趋势', desc: '总结 NeurIPS 2024 中 DPO 相关研究趋势，并列出代表性结论与过程。' },
                            { title: '评审观点对比', desc: '对比 NeurIPS 2024 中高分论文与低分论文的评审关注点差异。' },
                            { title: '某方向方法谱系', desc: '梳理 NeurIPS 2024 中 Agent/Tool Use 方向的方法谱系，并标出关键过程。' },
                          ].map((item, i) => (
                            <button
                              key={i}
                              onClick={() => setQuery(item.desc)}
                              className="bg-white/5 hover:bg-white/10 border border-border rounded-lg p-5 text-left transition-colors group"
                            >
                              <div className="text-lg font-medium text-accent-2 mb-2">{item.title}</div>
                              <div className="text-sm text-muted line-clamp-2">{item.desc}</div>
                              <div className="mt-3 text-sm text-accent opacity-0 group-hover:opacity-100 transition-opacity">使用这个示例 →</div>
                            </button>
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  </div>
                ) : (
                  <div className="w-full max-w-[95%] mx-auto pb-20 flex flex-col min-h-full">
                    {/* Job Progress Indicator - show when job is active */}
                    {(activeJobId && (polling || !jobState || jobState?.status === 'running')) && (
                      <div className="flex-1 flex items-start justify-center pt-[15vh]">
                        {jobState ? (
                          <div className="w-full">
                            <JobStatus job={jobState} />
                          </div>
                        ) : (
                          <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="bg-panel border border-border rounded-xl pt-6 pb-10 px-8 shadow-xl w-full max-w-md"
                          >
                            <div className="flex flex-col items-center justify-center gap-4">
                              <div className="w-10 h-10 border-3 border-accent border-t-transparent rounded-full animate-spin" />
                              <h3 className="font-semibold text-xl text-text">正在规划中</h3>
                              <p className="text-muted text-sm">AI 正在分析您的研究主题，请稍候</p>
                            </div>
                          </motion.div>
                        )}
                      </div>
                    )}

                    {/* Plan Editor UI */}
                    {jobState?.status === 'done' && jobState.type === 'plan' && (
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-8">
                        <div className="bg-panel-2 p-6 rounded-xl border border-border mb-6">
                          <h2 className="text-2xl font-bold text-accent-2 mb-6">编辑调研计划</h2>
                          <PlanEditor
                            plan={jobState.result.plan}
                            onUpdate={(newPlan) => {
                              setJobState(prev => ({ ...prev, result: { ...prev.result, plan: newPlan } }));
                            }}
                            onApprove={(finalPlan) => {
                              setJobState(prev => ({ ...prev, result: { ...prev.result, plan: finalPlan } }));
                              handleStartResearch();
                            }}
                          />
                        </div>
                      </motion.div>
                    )}

                    {/* Research Report Display */}
                    {/* Error View */}
                    {jobState?.status === 'error' && (
                      <div className="flex flex-col items-center justify-center p-8 mt-20 text-center">
                        <div className="text-6xl mb-4">❌</div>
                        <h2 className="text-2xl font-bold text-red-500 mb-2">任务执行出错</h2>
                        <div className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg max-w-2xl text-left font-mono text-sm text-red-300 whitespace-pre-wrap">
                          {jobState.error || jobState.message || "未知错误"}
                        </div>
                        <button
                          onClick={() => { setActiveJobId(null); setJobState(null); }}
                          className="mt-8 px-6 py-2 bg-white/10 hover:bg-white/20 rounded transition"
                        >
                          返回首页
                        </button>
                      </div>
                    )}



                    {/* Research Report Display */}
                    {jobState?.status === 'done' && (
                      <div className="mt-8 relative w-full">
                        {jobState.type === 'research' && (
                          <div className="h-[85vh]">
                            <ReportView
                              report={jobState.result.final_report}
                              verificationResult={jobState.result.verification_result}
                              onCitationClick={handleCitationClick}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Right Split View: Evidence Panel (Only show when research is done) */}
              {activeJobId && evidencePanelOpen && jobState?.status === 'done' && jobState?.type === 'research' && (
                <div className="w-80 border-l border-border bg-panel-2 flex flex-col shadow-xl md:relative right-0 h-full z-20">
                  <div className="p-4 border-b border-border flex justify-between items-center bg-panel">
                    <h3 className="font-bold text-accent-2 flex items-center gap-2"><Search size={16} /> 证据来源</h3>
                    <button onClick={() => setEvidencePanelOpen(false)} className="md:hidden"><X /></button>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                    {/* Check if we have structured Ref Items (Preferred) */}
                    {refItems.length > 0 ? (
                      <div className="space-y-4">
                        {refItems.map((ref, idx) => (
                          <div
                            key={idx}
                            id={`evidence-${ref.ref}`}
                            className={`p-3 rounded text-sm border transition-all cursor-pointer group
                                        ${selectedEvidence?.ref === ref.ref
                                ? 'bg-accent/10 border-accent shadow-[0_0_10px_rgba(var(--accent-rgb),0.1)]'
                                : 'bg-white/5 border-white/10 hover:border-accent/50'
                              }`}
                            onClick={() => setSelectedEvidence(ref)}
                          >
                            <div className="flex justify-between items-start mb-1 gap-2">
                              <div className="font-bold text-accent-2 bg-white/5 px-1.5 rounded text-xs leading-5 whitespace-nowrap">
                                {ref.ref}
                              </div>
                              {/* Jump Button */}
                              <button
                                onClick={(e) => handleJumpToPaper(ref.paper_id, e)}
                                className="text-muted hover:text-accent p-1 hover:bg-white/10 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                                title="跳转到知识库详情"
                              >
                                <ExternalLink size={14} />
                              </button>
                            </div>
                            <div className="text-xs font-semibold text-text mb-1 line-clamp-2" title={ref.title}>
                              {ref.title || 'Unknown Title'}
                            </div>
                            <div className="text-xs text-muted font-mono mb-2 truncate">
                              {ref.paper_id} · {ref.source}
                            </div>
                            <div className="line-clamp-4 text-muted text-xs leading-relaxed border-t border-white/5 pt-2 mt-2">
                              {ref.text}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      // Fallback to raw notes if ref_items missing
                      researchNotes.length === 0 ? (
                        <div className="text-muted text-sm text-center mt-10">暂无证据。</div>
                      ) : (
                        <div className="space-y-4">
                          {researchNotes.map((section, idx) => (
                            <div key={idx} className="space-y-2">
                              <h4 className="text-xs font-bold uppercase text-muted tracking-wider">{section.section}</h4>
                              {section.evidence?.map((ev, ei) => (
                                <div key={ei} className="bg-white/5 p-3 rounded text-sm border border-white/10 hover:border-accent/50 transition-colors cursor-pointer" onClick={() => setSelectedEvidence(ev)}>
                                  <div className="font-bold text-accent-2 mb-1 line-clamp-1">{ev.source || 'Source'}</div>
                                  <div className="line-clamp-3 text-muted">{ev.text}</div>
                                </div>
                              ))}
                            </div>
                          ))}
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {view === 'history' && <HistoryView onLoad={loadHistoryItem} />}
          {view === 'kb' && <KnowledgeBaseView initialPaperId={kbTargetPaperId} />}
        </div>
      </div>

      {showSettings && <SettingsView onClose={() => {
        setShowSettings(false);
        loadAppConfig(); // Refetch config when settings closed
      }} />}
    </div>
  );
}

function NavBtn({ icon, label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 p-3 rounded-lg w-full transition-all group",
        active ? "bg-accent/20 text-accent-2 border border-accent/30" : "text-muted hover:bg-white/5 hover:text-text"
      )}
    >
      <div className={cn("transition-transform group-hover:scale-110", active && "scale-110")}>{icon}</div>
      <span className="hidden md:block font-medium whitespace-nowrap">{label}</span>
    </button>
  );
}

function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}

export default App;
