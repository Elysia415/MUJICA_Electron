import React, { useState, useEffect, useRef } from 'react';
import { api } from './api';
import { JobStatus } from './components/JobStatus';
import { MarkdownRenderer } from './components/MarkdownRenderer';
import { Send, FileText, Database, PlusCircle, Settings, Play } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
  const [query, setQuery] = useState('');
  const [activeJobId, setActiveJobId] = useState(null);
  const [jobState, setJobState] = useState(null);
  const [view, setView] = useState('chat'); // chat, history, kb
  const [polling, setPolling] = useState(false);

  // Stats / Configuration (simplified)
  const [config, setConfig] = useState({
    model_name: 'gpt-4o',
    api_key: '', // user should input or load from env
    base_url: 'https://api.openai.com/v1',
  });

  const pollInterval = useRef(null);

  useEffect(() => {
    if (activeJobId && !polling) {
      setPolling(true);
      pollInterval.current = setInterval(async () => {
        try {
          const res = await api.getJob(activeJobId);
          setJobState(res.data);
          if (['done', 'error', 'cancelled'].includes(res.data.status)) {
            setPolling(false);
            clearInterval(pollInterval.current);
          }

          // Auto-trigger Research after Plan is done (Simplified flow)
          // In a real app, we would ask for approval.
          // For now, if plan is done, let's just show it.

        } catch (e) {
          console.error("Polling error", e);
        }
      }, 1000);
    }
    return () => clearInterval(pollInterval.current);
  }, [activeJobId, polling]);

  const handleStartPlan = async () => {
    if (!query.trim()) return;
    try {
      setJobState(null);
      const res = await api.startPlan(query, {
        model_name: config.model_name,
        api_key: config.api_key,
        base_url: config.base_url
      });
      setActiveJobId(res.data.job_id);
    } catch (e) {
      alert("Failed to start planning: " + e.message);
    }
  };

  const handleStartResearch = async () => {
    if (!jobState?.result?.plan) return;
    try {
      const res = await api.startResearch(jobState.result.plan, {
        model_name: config.model_name,
        chat_api_key: config.api_key,
        chat_base_url: config.base_url
      });
      setActiveJobId(res.data.job_id);
      setPolling(false); // Restart polling for new job
      setTimeout(() => setPolling(false), 100);
    } catch (e) {
      alert("Failed to start research: " + e.message);
    }
  };

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">
      {/* Sidebar */}
      <div className="w-16 md:w-64 bg-panel border-r border-border flex flex-col items-center md:items-stretch py-4">
        <div className="flex items-center justify-center p-2 mb-8">
          <div className="w-8 h-8 bg-accent rounded-full shadow-[0_0_15px_var(--accent)]" />
          <span className="hidden md:ml-3 font-bold text-xl tracking-widest text-accent-2">MUJICA</span>
        </div>

        <nav className="flex-1 flex flex-col gap-2 px-2">
          <NavBtn icon={<PlusCircle />} label="New Research" active={view === 'chat'} onClick={() => setView('chat')} />
          <NavBtn icon={<FileText />} label="History" active={view === 'history'} onClick={() => setView('history')} />
          <NavBtn icon={<Database />} label="Knowledge Base" active={view === 'kb'} onClick={() => setView('kb')} />
        </nav>

        <div className="px-2 mt-auto">
          <NavBtn icon={<Settings />} label="Settings" onClick={() => alert('Settings Dialog Placeholder')} />
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col relative bg-[url('/bg-noise.png')]">
        {/* Ambient Glows */}
        <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden z-0">
          <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-bg-glow-1 blur-[150px] opacity-40 rounded-full animate-pulse" />
          <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] bg-bg-glow-2 blur-[150px] opacity-30 rounded-full" />
        </div>

        <div className="z-10 flex-1 flex flex-col p-6 overflow-hidden">
          {view === 'chat' && (
            <div className="flex flex-col h-full max-w-5xl mx-auto w-full">
              {/* Output Area */}
              <div className="flex-1 overflow-y-auto mb-4 custom-scrollbar space-y-4">
                <AnimatePresence>
                  {!activeJobId && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center mt-20">
                      <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-2 mb-4">
                        What shall we discover?
                      </h1>
                      <p className="text-muted">Enter a research topic to generate a comprehensive report.</p>
                    </motion.div>
                  )}

                  {activeJobId && (
                    <div className="space-y-6">
                      <JobStatus job={jobState} />

                      {/* Plan Review Phase */}
                      {jobState?.status === 'done' && jobState.type === 'plan' && (
                        <motion.div
                          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                          className="bg-panel-2 p-6 rounded-xl border border-border"
                        >
                          <h2 className="text-xl font-bold text-accent-2 mb-4">Research Plan Generated</h2>
                          <MarkdownRenderer content={"```json\n" + JSON.stringify(jobState.result.plan, null, 2) + "\n```"} />
                          <div className="mt-4 flex gap-2">
                            <button
                              onClick={handleStartResearch}
                              className="flex items-center gap-2 bg-gradient-to-r from-accent to-[#5e001f] px-6 py-2 rounded-lg font-bold shadow-lg hover:shadow-accent/50 transition-all"
                            >
                              <Play size={18} /> Approver & Start Research
                            </button>
                          </div>
                        </motion.div>
                      )}

                      {/* Final Report Phase */}
                      {jobState?.status === 'done' && jobState.type === 'research' && (
                        <motion.div
                          initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                          className="bg-panel-2 p-8 rounded-xl border border-border shadow-2xl"
                        >
                          <h1 className="text-3xl font-bold text-accent-2 mb-6 border-b border-border pb-4">
                            Research Report
                          </h1>
                          <MarkdownRenderer content={jobState.result.final_report} />
                        </motion.div>
                      )}
                    </div>
                  )}
                </AnimatePresence>
              </div>

              {/* Input Area */}
              <div className="bg-panel border border-border rounded-xl p-2 flex items-center gap-2 shadow-2xl">
                <input
                  type="text"
                  className="flex-1 bg-transparent border-none outline-none text-text px-4 py-2 placeholder-muted"
                  placeholder="Describe your research goal..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleStartPlan()}
                />
                <button
                  onClick={handleStartPlan}
                  className="p-2 bg-accent rounded-lg text-white hover:bg-accent-hover transition-colors"
                >
                  <Send size={20} />
                </button>
              </div>
            </div>
          )}

          {view === 'history' && <div className="text-center text-muted mt-20">History Feature Coming Soon</div>}
          {view === 'kb' && <div className="text-center text-muted mt-20">Knowledge Base Management Coming Soon</div>}
        </div>
      </div>
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
      <span className="hidden md:block font-medium">{label}</span>
    </button>
  );
}

export default App;
