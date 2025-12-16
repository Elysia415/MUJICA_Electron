import React, { useState, useEffect, useRef } from 'react';
import { api } from './api';
import { JobStatus } from './components/JobStatus';
import { MarkdownRenderer } from './components/MarkdownRenderer';
import { KnowledgeBaseView } from './components/KnowledgeBaseView';
import { SettingsView } from './components/SettingsView';
import { HistoryView } from './components/HistoryView';
import { PlanEditor } from './components/PlanEditor';
import { useTheme } from './components/ThemeProvider';
import { Send, FileText, Database, PlusCircle, Settings, Play, BookOpen, Search, X, Sun, Moon } from 'lucide-react';
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

  // Configuration
  const [config, setConfig] = useState({
    model_name: 'gpt-4o',
    api_key: '',
    base_url: 'https://api.openai.com/v1',
  });

  const pollInterval = useRef(null);

  // Initial Config Load
  useEffect(() => {
    api.getConfig().then(res => {
      // Only override if not set by user (simple logic)
      setConfig(prev => ({ ...prev, ...res.data }));
    }).catch(console.error);
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
        model_name: config.MUJICA_DEFAULT_MODEL || 'gpt-4o',
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
    // Note: This is an MVP restoration. Real "resume" might need more state.
    // We map the snapshot to view state.
    setQuery('');
    // Mapping logic: if data defines final_report, show it.
    // We reconstruct a fake jobState to display the result
    const restoredJob = {
      status: 'done',
      type: 'research', // Assume research for now
      result: {
        plan: data.pending_plan,
        research_notes: data.research_notes,
        final_report: data.final_report,
        verification_result: data.verification_result
      }
    };
    setJobState(restoredJob);
    setActiveJobId('RESTORED_HISTORY');
    setView('chat');
  };

  // Helper to extract evidence from notes based on chunk_id (used when clicking citations)
  // For MVP: We just show all evidence in the side panel or filter if implemented.
  const researchNotes = jobState?.result?.research_notes || [];

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden font-sans">
      {/* Sidebar */}
      <div className="w-16 md:w-64 bg-panel border-r border-border flex flex-col items-center md:items-stretch py-4 z-20 shadow-xl">
        <div className="flex items-center justify-center p-2 mb-8">
          <img src="/logo.png" alt="MUJICA" className="w-8 h-8 rounded-lg shadow-[0_0_15px_var(--accent)]" />
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
                  <div className="w-full max-w-4xl mx-auto pb-20 flex flex-col min-h-full">
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
                    {jobState?.status === 'done' && jobState.type === 'research' && (
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-8">
                        <div className="bg-panel-2 p-8 rounded-xl border border-border shadow-2xl mb-8">
                          <div className="flex justify-between items-center mb-6 pb-4 border-b border-border">
                            <h1 className="text-4xl font-bold text-accent-2">
                              最终报告
                            </h1>
                            <button
                              onClick={() => {
                                const blob = new Blob([jobState.result.final_report], { type: 'text/markdown' });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = `MUJICA_Report_${Date.now()}.md`;
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                              }}
                              className="px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg flex items-center gap-2 transition-colors"
                            >
                              <Download size={18} /> 导出 MD
                            </button>
                          </div>

                          <div className="text-lg leading-relaxed content-markdown">
                            <MarkdownRenderer content={jobState.result.final_report} />
                          </div>

                          {/* Verification Results */}
                          {jobState.result.verification_result && (
                            <div className="mt-8 pt-8 border-t border-border">
                              <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                                <span className="text-green-400">✓</span> 验证报告
                              </h3>
                              <div className="bg-black/30 p-6 rounded-lg font-mono text-sm whitespace-pre-wrap border border-white/5">
                                <div className="text-lg font-bold text-accent mb-4 border-b border-white/10 pb-2">
                                  信任评分: {jobState.result.verification_result.score}/10
                                </div>
                                <div className="text-muted leading-relaxed">
                                  {jobState.result.verification_result.comment || "暂无详细评语"}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
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
                    {researchNotes.length === 0 ? (
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
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {view === 'history' && <HistoryView onLoad={loadHistoryItem} />}
          {view === 'kb' && <KnowledgeBaseView />}
        </div>
      </div>

      {showSettings && <SettingsView onClose={() => setShowSettings(false)} />}
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
