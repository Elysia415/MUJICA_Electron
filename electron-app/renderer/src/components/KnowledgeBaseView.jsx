import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import { Trash2, RefreshCw, Download, Upload, Search, Plus, FileCheck, X, ExternalLink, Filter, BarChart3 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useConfirm, useToast } from './Dialog';

export function KnowledgeBaseView({ initialPaperId }) {
    const [papers, setPapers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState('');
    const [ingestModalOpen, setIngestModalOpen] = useState(false);
    const [selectedPaper, setSelectedPaper] = useState(null);

    // Handle external navigation (from Evidence Panel)
    useEffect(() => {
        if (initialPaperId) {
            console.log("Navigating to paper:", initialPaperId);
            // Must fetch details first or find in list.
            // Simplified: direct API fetch.
            api.getPaperDetail(initialPaperId).then(res => {
                setSelectedPaper(res.data);
            }).catch(e => {
                console.error("Failed to load target paper:", e);
                // Try fallback to list find
                const found = papers.find(p => p.id === initialPaperId);
                if (found) setSelectedPaper(found);
            });
        }
    }, [initialPaperId]);

    // Batch selection
    const [selectedIds, setSelectedIds] = useState(new Set());

    // Filters
    const [filterYear, setFilterYear] = useState('');
    const [filterVenue, setFilterVenue] = useState('');
    const [filterDecision, setFilterDecision] = useState('');
    const [showFilters, setShowFilters] = useState(false);

    // Stats
    const [stats, setStats] = useState({ papers: 0, reviews: 0, chunks: 0 });

    // Semantic Search Mode
    const [searchMode, setSearchMode] = useState('keyword'); // 'keyword' or 'semantic'
    const [semanticLoading, setSemanticLoading] = useState(false);

    // Custom dialog hooks (replacing native alert/confirm)
    const { confirm, dialog: confirmDialog } = useConfirm();
    const { show: showToast, toast } = useToast();

    const fetchPapers = async () => {
        setLoading(true);
        try {
            if (searchMode === 'semantic' && search.trim()) {
                // Use semantic search API
                setSemanticLoading(true);
                const res = await api.semanticSearchPapers(search, 50);
                setPapers(res.data.papers);
                setSemanticLoading(false);
            } else {
                // Use keyword search API
                const res = await api.listPapers(500, search);
                setPapers(res.data.papers);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
            setSemanticLoading(false);
        }
    };


    const fetchStats = async () => {
        try {
            const res = await api.getKBStats();
            setStats(res.data);
        } catch (e) {
            console.error('Stats fetch failed:', e);
        }
    };

    useEffect(() => {
        fetchPapers();
        fetchStats();
    }, [search, searchMode]);

    // Derive unique filter options from papers
    const yearOptions = [...new Set(papers.map(p => p.year).filter(Boolean))].sort((a, b) => b - a);
    const venueOptions = [...new Set(papers.map(p => p.venue_id).filter(Boolean))].slice(0, 20);
    const decisionOptions = [...new Set(papers.map(p => p.decision).filter(Boolean))];

    // Apply client-side filters
    const filteredPapers = papers.filter(p => {
        if (filterYear && p.year != filterYear) return false;
        if (filterVenue && !p.venue_id?.includes(filterVenue)) return false;
        if (filterDecision && p.decision !== filterDecision) return false;
        return true;
    });

    const handleDelete = async (id, e) => {
        e?.stopPropagation();
        const confirmed = await confirm({
            title: '删除论文',
            message: '确定删除这篇论文吗？此操作不可撤销。',
            danger: true
        });
        if (!confirmed) return;
        try {
            await api.deletePaper(id);
            fetchPapers();
            fetchStats();
            if (selectedPaper?.id === id) setSelectedPaper(null);
            setSelectedIds(prev => { prev.delete(id); return new Set(prev); });
            showToast('论文已删除', 'success');
        } catch (e) {
            showToast('删除失败: ' + e.message, 'error');
        }
    };

    const handleBatchDelete = async () => {
        if (selectedIds.size === 0) return;
        const confirmed = await confirm({
            title: '批量删除',
            message: `确定删除选中的 ${selectedIds.size} 篇论文吗？此操作不可撤销。`,
            danger: true
        });
        if (!confirmed) return;
        try {
            for (const id of selectedIds) {
                await api.deletePaper(id);
            }
            setSelectedIds(new Set());
            fetchPapers();
            fetchStats();
            showToast(`已删除 ${selectedIds.size} 篇论文`, 'success');
        } catch (e) {
            showToast('批量删除失败: ' + e.message, 'error');
        }
    };

    const toggleSelect = (id, e) => {
        e.stopPropagation();
        setSelectedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (selectedIds.size === filteredPapers.length) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(filteredPapers.map(p => p.id)));
        }
    };

    const [exporting, setExporting] = useState(false);
    const [importing, setImporting] = useState(false);
    const [progress, setProgress] = useState(0);
    const [exportSuccess, setExportSuccess] = useState(null);
    const [exportConfirmOpen, setExportConfirmOpen] = useState(false);

    // Export & Import Handlers
    const fileInputRef = useRef(null);

    const handleExport = () => {
        setExportConfirmOpen(true);
    };

    const executeExport = async () => {
        setExportConfirmOpen(false);

        console.log("[Export] handleExport called (Local Mode)");
        setExporting(true);
        setProgress(0);
        try {
            console.log("[Export] Calling api.exportKBLocal...");
            await api.exportKBLocal((p) => {
                if (p.error) throw new Error(p.error);

                if (typeof p.progress === 'number') {
                    setProgress(p.progress);
                }

                if (p.path) {
                    setExportSuccess({ path: p.path, dir: p.dir });
                }
            });
        } catch (err) {
            console.error("Export failed", err);
            showToast("导出失败: " + (err.message), 'error');
        } finally {
            setExporting(false);
            setProgress(0);
        }
    };

    const handleImportClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const confirmed = await confirm({
            title: '导入知识库',
            message: '导入将合并数据到当前知识库。\n建议先导出备份当前数据。\n\n确定要继续吗？'
        });
        if (!confirmed) {
            e.target.value = null;
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        setImporting(true);
        setProgress(0);
        try {
            await api.importKB(formData, (p) => {
                setProgress(Math.round((p.loaded * 100) / p.total));
            });
            showToast("导入且合并成功！", 'success');
            fetchPapers();
            fetchStats();
        } catch (err) {
            console.error("Import failed", err);
            showToast("导入失败: " + (err.response?.data?.detail || err.message), 'error');
        } finally {
            setImporting(false);
            setProgress(0);
            e.target.value = null;
        }
    };

    return (
        <>
            {confirmDialog}
            {toast}
            <div className="h-full flex flex-col p-6 max-w-6xl mx-auto w-full">
                {/* Hidden File Input */}
                <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    accept=".zip"
                    className="hidden"
                />

                {/* Header */}
                <div className="flex justify-between items-center mb-4">
                    <h1 className="text-3xl font-bold text-accent-2">知识库</h1>
                    <div className="flex gap-2">
                        <button
                            onClick={handleExport}
                            className="p-2 text-muted hover:text-accent rounded-lg hover:bg-white/5 transition-colors"
                            title="导出备份 (ZIP)"
                        >
                            <Download size={18} />
                        </button>
                        <button
                            onClick={handleImportClick}
                            className="p-2 text-muted hover:text-accent rounded-lg hover:bg-white/5 transition-colors"
                            title="导入合并 (ZIP)"
                        >
                            <Upload size={18} />
                        </button>
                        <div className="w-px h-8 bg-white/10 mx-1"></div>
                        <button
                            onClick={() => setIngestModalOpen(true)}
                            className="flex items-center gap-2 bg-accent px-4 py-2 rounded-lg text-white hover:bg-accent-hover transition-colors"
                        >
                            <Plus size={18} /> 导入论文
                        </button>
                    </div>
                </div>

                {/* Stats Overview */}
                <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="bg-panel border border-border rounded-lg p-3 flex items-center gap-3">
                        <BarChart3 size={20} className="text-accent" />
                        <div>
                            <div className="text-2xl font-bold text-text">{stats.papers || papers.length}</div>
                            <div className="text-xs text-muted">论文</div>
                        </div>
                    </div>
                    <div className="bg-panel border border-border rounded-lg p-3 flex items-center gap-3">
                        <FileCheck size={20} className="text-green-400" />
                        <div>
                            <div className="text-2xl font-bold text-text">{stats.reviews || 0}</div>
                            <div className="text-xs text-muted">评审</div>
                        </div>
                    </div>
                    <div className="bg-panel border border-border rounded-lg p-3 flex items-center gap-3">
                        <Search size={20} className="text-blue-400" />
                        <div>
                            <div className="text-2xl font-bold text-text">{stats.chunks || 0}</div>
                            <div className="text-xs text-muted">向量 Chunks</div>
                        </div>
                    </div>
                </div>

                {/* Search + Filter Toggle */}
                <div className="flex gap-2 mb-2">
                    <div className="flex-1 bg-panel border border-border rounded-lg flex items-center px-3 py-2">
                        <Search size={18} className="text-muted mr-2" />
                        <input
                            type="text"
                            placeholder={searchMode === 'semantic' ? '语义搜索（理解含义）...' : '关键词搜索（匹配标题）...'}
                            className="bg-transparent outline-none flex-1 text-text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        {semanticLoading && <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin mr-2"></div>}
                    </div>
                    {/* Semantic Search Toggle */}
                    <button
                        onClick={() => setSearchMode(searchMode === 'keyword' ? 'semantic' : 'keyword')}
                        className={`px-3 py-2 border border-border rounded-lg transition-all text-sm font-medium flex items-center gap-1.5
                        ${searchMode === 'semantic'
                                ? 'bg-accent/20 text-accent border-accent/50'
                                : 'bg-panel text-muted hover:text-text hover:bg-white/5'}`}
                        title={searchMode === 'semantic' ? '当前：语义搜索（向量）' : '当前：关键词搜索'}
                    >
                        {searchMode === 'semantic' ? '🧠 语义' : '🔤 关键词'}
                    </button>
                    <button
                        onClick={() => setShowFilters(!showFilters)}
                        className={`p-2 border border-border rounded-lg transition-colors ${showFilters ? 'bg-accent/20 text-accent' : 'bg-panel text-muted hover:text-text'}`}
                    >
                        <Filter size={18} />
                    </button>
                    <button onClick={() => { fetchPapers(); fetchStats(); }} className="p-2 bg-panel border border-border rounded-lg text-muted hover:text-text hover:bg-white/5">
                        <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                </div>

                {/* Filter Panel */}
                {showFilters && (
                    <div className="bg-panel border border-border rounded-lg p-3 mb-4 flex gap-4 flex-wrap items-center">
                        <div>
                            <label className="text-xs text-muted mr-2">年份:</label>
                            <select value={filterYear} onChange={e => setFilterYear(e.target.value)} className="bg-black/40 border border-border rounded px-2 py-1 text-sm text-text">
                                <option value="">全部</option>
                                {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted mr-2">会议:</label>
                            <select value={filterVenue} onChange={e => setFilterVenue(e.target.value)} className="bg-black/40 border border-border rounded px-2 py-1 text-sm text-text">
                                <option value="">全部</option>
                                {venueOptions.map(v => <option key={v} value={v}>{v}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted mr-2">决策:</label>
                            <select value={filterDecision} onChange={e => setFilterDecision(e.target.value)} className="bg-black/40 border border-border rounded px-2 py-1 text-sm text-text">
                                <option value="">全部</option>
                                {decisionOptions.map(d => <option key={d} value={d}>{d}</option>)}
                            </select>
                        </div>
                        <button onClick={() => { setFilterYear(''); setFilterVenue(''); setFilterDecision(''); }} className="text-xs text-accent hover:underline">
                            清除筛选
                        </button>
                    </div>
                )}

                {/* Batch Actions */}
                {selectedIds.size > 0 && (
                    <div className="bg-accent/10 border border-accent/30 rounded-lg p-3 mb-4 flex items-center justify-between">
                        <span className="text-sm text-accent-2">已选中 {selectedIds.size} 篇论文</span>
                        <div className="flex gap-2">
                            <button onClick={() => setSelectedIds(new Set())} className="text-sm text-muted hover:text-text">
                                取消选择
                            </button>
                            <button onClick={handleBatchDelete} className="px-3 py-1 bg-red-500/20 text-red-400 rounded text-sm hover:bg-red-500/30">
                                批量删除
                            </button>
                        </div>
                    </div>
                )}

                {/* Papers Table */}
                <div className="flex-1 overflow-auto bg-panel-2 border border-border rounded-xl">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b border-border text-muted">
                                <th className="p-4 font-medium w-10">
                                    <input
                                        type="checkbox"
                                        checked={filteredPapers.length > 0 && selectedIds.size === filteredPapers.length}
                                        onChange={toggleSelectAll}
                                        className="accent-accent"
                                    />
                                </th>
                                <th className="p-4 font-medium">标题</th>
                                <th className="p-4 font-medium">会议/期刊</th>
                                <th className="p-4 font-medium">结果</th>
                                <th className="p-4 font-medium">评分</th>
                                <th className="p-4 font-medium text-right">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredPapers.map((p) => (
                                <tr
                                    key={p.id}
                                    className={`border-b border-border/50 hover:bg-white/5 transition-colors group cursor-pointer ${selectedIds.has(p.id) ? 'bg-accent/5' : ''}`}
                                    onClick={() => setSelectedPaper(p)}
                                >
                                    <td className="p-4" onClick={e => e.stopPropagation()}>
                                        <input
                                            type="checkbox"
                                            checked={selectedIds.has(p.id)}
                                            onChange={e => toggleSelect(p.id, e)}
                                            className="accent-accent"
                                        />
                                    </td>
                                    <td className="p-4">
                                        <div className="font-medium text-text line-clamp-1" title={p.title}>{p.title}</div>
                                        <div className="text-xs text-muted font-mono mt-1">{p.id}</div>
                                    </td>
                                    <td className="p-4 text-sm">{p.venue_id} <span className="text-muted">({p.year})</span></td>
                                    <td className="p-4">
                                        <span className={`text-xs px-2 py-1 rounded-full border whitespace-nowrap ${p.decision?.toLowerCase().includes('accept')
                                            ? 'bg-green-500/10 border-green-500/30 text-green-400'
                                            : 'bg-red-500/10 border-red-500/30 text-red-400'
                                            }`}>
                                            {p.decision || 'Unknown'}
                                        </span>
                                    </td>
                                    <td className="p-4 font-mono text-accent-2">{p.rating || '-'}</td>
                                    <td className="p-4 text-right">
                                        <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={(e) => handleDelete(p.id, e)}
                                                className="p-1.5 text-red-400 hover:bg-red-500/20 rounded transition-colors" title="Delete">
                                                <Trash2 size={16} />
                                            </button>
                                            {p.pdf_path && (
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        api.openPdf(p.pdf_path).catch(err => {
                                                            showToast(`打开 PDF 失败: ${err.response?.data?.detail || err.message}`, 'error');
                                                        });
                                                    }}
                                                    className="p-1.5 text-green-400 hover:bg-green-500/20 rounded transition-colors"
                                                    title="打开 PDF"
                                                >
                                                    <FileCheck size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {filteredPapers.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={6} className="p-8 text-center text-muted">未找到论文。</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Loading Overlay */}
                {(exporting || importing) && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
                        <div className="bg-panel p-6 rounded-xl border border-border shadow-2xl flex flex-col items-center gap-4 min-w-[300px]">
                            <RefreshCw size={32} className="animate-spin text-accent" />
                            <div className="text-lg font-medium text-white">
                                {exporting ? "正在打包数据库..." : "正在合并数据库..."}
                            </div>
                            <div className="text-sm text-muted text-center leading-relaxed">
                                {exporting
                                    ? "数据量较大时可能需要几分钟\n请不要关闭窗口"
                                    : "正在处理向量索引合并\n请耐心等待，勿关闭窗口"}
                            </div>

                            {/* Progress Bar */}
                            <div className="w-64">
                                <div className="h-1.5 bg-white/10 rounded-full overflow-hidden mb-2">
                                    <div
                                        className="h-full bg-accent transition-all duration-300 ease-out"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                                <div className="flex justify-between text-xs text-muted">
                                    <span>{exporting ? '下载中' : '上传中'}</span>
                                    <span className="font-mono">{progress}%</span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Export Success Modal */}
                <AnimatePresence>
                    {exportSuccess && (
                        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="bg-panel border border-white/10 rounded-xl shadow-2xl max-w-md w-full overflow-hidden"
                                onClick={e => e.stopPropagation()}
                            >
                                <div className="p-8 text-center flex flex-col items-center">
                                    <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mb-6 text-green-400 shadow-[0_0_20px_rgba(74,222,128,0.2)]">
                                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                    </div>
                                    <h3 className="text-2xl font-bold text-white mb-2">导出成功!</h3>
                                    <p className="text-muted text-sm mb-6">数据库备份已生成</p>

                                    <div className="text-left w-full bg-black/30 p-4 rounded-lg border border-white/5 mb-8 overflow-hidden">
                                        <div className="text-xs text-muted uppercase tracking-wider mb-1 font-bold">保存路径</div>
                                        <div className="text-xs text-accent-2 font-mono break-all leading-relaxed">
                                            {exportSuccess.path}
                                        </div>
                                    </div>

                                    <div className="flex gap-3 w-full">
                                        <button
                                            onClick={() => setExportSuccess(null)}
                                            className="flex-1 px-4 py-3 rounded-lg text-sm font-medium text-muted hover:text-white hover:bg-white/5 transition-colors"
                                        >
                                            关闭
                                        </button>
                                        <button
                                            onClick={() => {
                                                api.openFolder(exportSuccess.dir);
                                                setExportSuccess(null);
                                            }}
                                            className="flex-[2] px-4 py-3 rounded-lg text-sm font-bold bg-accent hover:bg-accent-hover text-white shadow-lg shadow-accent/20 transition-all flex items-center justify-center gap-2"
                                        >
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                                            打开文件夹
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>



                {/* Export Confirm Modal */}
                <AnimatePresence>
                    {exportConfirmOpen && (
                        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="bg-panel border border-border rounded-xl shadow-2xl max-w-sm w-full overflow-hidden"
                                onClick={e => e.stopPropagation()}
                            >
                                <div className="p-6">
                                    <h3 className="text-lg font-bold text-white mb-2">确认导出?</h3>
                                    <div className="text-sm text-muted leading-relaxed mb-6">
                                        即将执行本地极速导出。<br />
                                        文件将保存至 <span className="text-accent-2 font-mono ml-1">Desktop/MUJICA_Backups</span> 目录。
                                    </div>
                                    <div className="flex gap-3 justify-end">
                                        <button
                                            onClick={() => setExportConfirmOpen(false)}
                                            className="px-4 py-2 text-sm text-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors border border-transparent hover:border-white/10"
                                        >
                                            取消
                                        </button>
                                        <button
                                            onClick={executeExport}
                                            className="px-4 py-2 text-sm font-bold bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors shadow-lg shadow-accent/20"
                                        >
                                            确认导出
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>

                <AnimatePresence>
                    {ingestModalOpen && <IngestModal onClose={() => setIngestModalOpen(false)} onIngest={() => { setIngestModalOpen(false); fetchPapers(); fetchStats(); }} />}
                    {selectedPaper && <PaperDetailModal paper={selectedPaper} onClose={() => setSelectedPaper(null)} onDelete={(id) => handleDelete(id)} />}
                </AnimatePresence>
            </div>
        </>
    );
}

// Paper Detail Modal Component
function PaperDetailModal({ paper, onClose, onDelete }) {
    const [fullPaper, setFullPaper] = useState(null);
    const [loading, setLoading] = useState(true);

    // Fetch full paper details including reviews
    useEffect(() => {
        const fetchDetails = async () => {
            try {
                const res = await api.getPaperDetail(paper.id);
                setFullPaper(res.data);
            } catch (e) {
                console.error('Failed to fetch paper details:', e);
                setFullPaper(paper); // Fallback to basic paper data
            } finally {
                setLoading(false);
            }
        };
        fetchDetails();
    }, [paper.id]);

    const p = fullPaper || paper;
    const openReviewUrl = `https://openreview.net/forum?id=${p.id}`;

    // Format authors array
    const authorsDisplay = Array.isArray(p.authors)
        ? p.authors.join(', ')
        : (p.authors || '');

    // Format keywords array
    const keywordsArray = Array.isArray(p.keywords)
        ? p.keywords
        : (p.keywords ? String(p.keywords).split(/[,;、]/) : []);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
                className="bg-panel border border-border rounded-xl w-full max-w-4xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="p-5 border-b border-border bg-panel-2 flex justify-between items-start gap-4">
                    <div className="flex-1 min-w-0">
                        <h2 className="text-lg font-bold text-text leading-tight">{p.title}</h2>
                        <p className="text-sm text-muted mt-1 font-mono">{p.id}</p>
                    </div>
                    <button onClick={onClose} className="text-muted hover:text-text text-xl shrink-0 p-1">
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
                    {loading ? (
                        <div className="flex items-center justify-center py-8">
                            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                        </div>
                    ) : (
                        <>
                            {/* Metadata Row */}
                            <div className="flex flex-wrap gap-4 items-center">
                                <span className={`text-xs px-3 py-1 rounded-full border font-medium whitespace-nowrap ${p.decision?.toLowerCase().includes('accept')
                                    ? 'bg-green-500/10 border-green-500/30 text-green-400'
                                    : 'bg-red-500/10 border-red-500/30 text-red-400'
                                    }`}>
                                    {p.decision || 'Unknown'}
                                </span>
                                {p.presentation && (
                                    <span className="text-xs px-2 py-1 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">
                                        {p.presentation}
                                    </span>
                                )}
                                <span className="text-sm text-muted">{p.venue_id} ({p.year})</span>
                                {p.rating && <span className="text-sm font-mono text-accent-2">评分: {p.rating}</span>}
                                {p.pdf_path && <span className="text-sm text-green-400">📄 PDF</span>}
                            </div>

                            {/* Authors */}
                            {authorsDisplay && (
                                <div>
                                    <h3 className="text-sm font-semibold text-muted mb-2">👤 作者</h3>
                                    <p className="text-text text-sm">{authorsDisplay}</p>
                                </div>
                            )}

                            {/* Abstract */}
                            {p.abstract && (
                                <div>
                                    <h3 className="text-sm font-semibold text-muted mb-2">📝 摘要</h3>
                                    <p className="text-text text-sm leading-relaxed bg-black/20 p-4 rounded-lg whitespace-pre-wrap">{p.abstract}</p>
                                </div>
                            )}

                            {/* Keywords */}
                            {keywordsArray.length > 0 && (
                                <div>
                                    <h3 className="text-sm font-semibold text-muted mb-2">🏷️ 关键词</h3>
                                    <div className="flex flex-wrap gap-2">
                                        {keywordsArray.map((kw, i) => (
                                            <span key={i} className="text-xs bg-accent/20 text-accent-2 px-2 py-1 rounded">{String(kw).trim()}</span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Decision Note */}
                            {p.decision_text && (
                                <div>
                                    <h3 className="text-sm font-semibold text-green-400 mb-2">✅ Decision Note</h3>
                                    <div className="text-text text-sm leading-relaxed bg-green-500/10 border border-green-500/20 p-4 rounded-lg whitespace-pre-wrap">
                                        {p.decision_text}
                                    </div>
                                </div>
                            )}

                            {/* Rebuttal */}
                            {p.rebuttal_text && (
                                <div>
                                    <h3 className="text-sm font-semibold text-yellow-400 mb-2">💬 Rebuttal</h3>
                                    <div className="text-text text-sm leading-relaxed bg-yellow-500/10 border border-yellow-500/20 p-4 rounded-lg whitespace-pre-wrap max-h-64 overflow-y-auto">
                                        {p.rebuttal_text}
                                    </div>
                                </div>
                            )}

                            {/* Reviews */}
                            {p.reviews && p.reviews.length > 0 && (
                                <div>
                                    <h3 className="text-sm font-semibold text-muted mb-3">📋 Reviews ({p.reviews.length})</h3>
                                    <div className="space-y-4">
                                        {p.reviews.map((r, idx) => (
                                            <div key={idx} className="bg-white/5 border border-border rounded-lg p-4">
                                                <div className="flex items-center gap-4 mb-3 text-sm">
                                                    <span className="text-muted">Review #{idx + 1}</span>
                                                    {r.rating_raw && <span className="text-accent-2 font-mono">评分: {r.rating_raw}</span>}
                                                    {r.confidence_raw && <span className="text-muted">置信度: {r.confidence_raw}</span>}
                                                </div>
                                                {r.summary && (
                                                    <div className="mb-2">
                                                        <span className="text-xs text-muted font-semibold">Summary:</span>
                                                        <p className="text-sm text-text mt-1">{r.summary}</p>
                                                    </div>
                                                )}
                                                {r.strengths && (
                                                    <div className="mb-2">
                                                        <span className="text-xs text-green-400 font-semibold">Strengths:</span>
                                                        <p className="text-sm text-text mt-1 whitespace-pre-wrap">{r.strengths}</p>
                                                    </div>
                                                )}
                                                {r.weaknesses && (
                                                    <div className="mb-2">
                                                        <span className="text-xs text-red-400 font-semibold">Weaknesses:</span>
                                                        <p className="text-sm text-text mt-1 whitespace-pre-wrap">{r.weaknesses}</p>
                                                    </div>
                                                )}
                                                {r.text && !r.summary && !r.strengths && !r.weaknesses && (
                                                    <p className="text-sm text-text whitespace-pre-wrap max-h-48 overflow-y-auto">{r.text}</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-border bg-panel-2 flex justify-between items-center">
                    <button
                        onClick={() => { onDelete?.(p.id); onClose(); }}
                        className="px-4 py-2 text-red-400 hover:bg-red-500/20 rounded transition-colors text-sm"
                    >
                        🗑️ 删除论文
                    </button>
                    <a
                        href={openReviewUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors text-sm"
                    >
                        <ExternalLink size={16} /> 在 OpenReview 查看
                    </a>
                </div>
            </motion.div>
        </div>
    );
}


function IngestModal({ onClose, onIngest }) {
    // 1. Venue Selection State
    const [venueMode, setVenueMode] = useState('hotpick'); // 'hotpick' | 'custom'
    const [hotpickConf, setHotpickConf] = useState('NeurIPS');
    const [hotpickYear, setHotpickYear] = useState(2024);
    const [hotpickTrack, setHotpickTrack] = useState('Conference');
    const [customVenueId, setCustomVenueId] = useState('NeurIPS.cc/2024/Conference'); // Default fallback

    // 2. Scope & Limits State
    const [fetchScope, setFetchScope] = useState('accepted_only'); // 'all' | 'accepted_only'
    const [fetchAllAc, setFetchAllAc] = useState(false);
    const [limit, setLimit] = useState(50);
    const [skipExisting, setSkipExisting] = useState(false);

    // 3. PDF & Processing State
    const [downloadPdf, setDownloadPdf] = useState(true);
    const [parsePdf, setParsePdf] = useState(true);
    const [maxPages, setMaxPages] = useState(12);

    // 4. Advanced / Other
    const [presentation, setPresentation] = useState(['oral', 'spotlight', 'poster', 'unknown']);

    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState('');

    // Job tracking state
    const [activeJobId, setActiveJobId] = useState(null);
    const [jobProgress, setJobProgress] = useState(null);

    // Poll job status when activeJobId is set
    useEffect(() => {
        if (!activeJobId) return;

        const interval = setInterval(async () => {
            try {
                const res = await api.getJob(activeJobId);
                const job = res.data;
                setJobProgress(job);
                setStatus(job.message || '进行中...');

                if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') {
                    clearInterval(interval);
                    setLoading(false);
                    if (job.status === 'done') {
                        // Refresh KB connection to see new data, then close modal
                        setTimeout(async () => {
                            try { await api.refreshKB(); } catch (e) { console.error('RefreshKB:', e); }
                            onIngest();
                        }, 1000);
                    }
                }
            } catch (e) {
                console.error('Poll error:', e);
            }
        }, 1000);

        return () => clearInterval(interval);
    }, [activeJobId]);

    // Derived Venue ID
    const getVenueId = () => {
        if (venueMode === 'custom') return customVenueId;
        const confMap = {
            'NeurIPS': 'NeurIPS.cc',
            'ICLR': 'ICLR.cc',
            'ICML': 'ICML.cc',
            'CoRL': 'CoRL.cc',
            'COLM': 'COLM.cc',
            'CVPR': 'thecvf.com/CVPR', // Note: CVPR format varies, sticking to simple logic for now or user uses custom
            'ICCV': 'thecvf.com/ICCV',
        };
        const root = confMap[hotpickConf] || `${hotpickConf}.cc`;
        return `${root}/${hotpickYear}/${hotpickTrack}`;
    };

    const handleRun = async () => {
        const venueId = getVenueId();
        if (!venueId) {
            showToast('Venue ID 不能为空', 'warning');
            return;
        }

        setLoading(true);
        setStatus('读取配置...');
        setJobProgress(null);
        setActiveJobId(null);

        // Fetch saved config to get embedding settings
        let config = {};
        try {
            const configRes = await api.getConfig();
            config = configRes.data || {};
        } catch (e) {
            console.warn('Failed to load config, using defaults:', e);
        }

        setStatus('任务排队中...');

        const payload = {
            venue_id: venueId,
            limit: fetchAllAc ? null : parseInt(limit),
            accepted_only: fetchAllAc ? true : (fetchScope === 'accepted_only'),
            skip_existing: skipExisting,
            download_pdfs: downloadPdf,
            parse_pdfs: downloadPdf && parsePdf, // parse depends on download
            max_pdf_pages: parseInt(maxPages),
            presentation_in: presentation,
            // Hidden/Advanced defaults
            max_downloads: fetchAllAc ? null : (downloadPdf ? parseInt(limit) : null),
            // Embedding settings from saved config
            embedding_model: config.MUJICA_EMBEDDING_MODEL || 'text-embedding-3-small',
            embedding_api_key: config.MUJICA_EMBEDDING_API_KEY || config.OPENAI_API_KEY || null,
            embedding_base_url: config.MUJICA_EMBEDDING_BASE_URL || config.OPENAI_BASE_URL || null,
        };

        try {
            const res = await api.startIngest(venueId, payload);
            setActiveJobId(res.data.job_id);
            setStatus(`任务已启动 (ID: ${res.data.job_id})`);
        } catch (e) {
            setStatus('错误: ' + e.message);
            setLoading(false);
        }
    };

    // Progress bar helper
    const ProgressBar = ({ label, current, total, stage }) => {
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;
        const isActive = jobProgress?.progress?.[stage];
        if (!isActive && current === 0) return null;

        return (
            <div className="space-y-1">
                <div className="flex justify-between text-xs text-muted">
                    <span>{label}</span>
                    <span>{current}/{total} ({percent}%)</span>
                </div>
                <div className="h-2 bg-black/40 rounded-full overflow-hidden">
                    <div
                        className="h-full bg-accent transition-all duration-300"
                        style={{ width: `${percent}%` }}
                    />
                </div>
            </div>
        );
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
                className="bg-panel border border-border rounded-xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
            >
                <div className="p-5 border-b border-border bg-panel-2 flex justify-between items-center">
                    <h2 className="text-xl font-bold flex items-center gap-2">
                        <Plus size={20} className="text-accent" /> 导入论文 (Ingest)
                    </h2>
                    <button onClick={onClose} className="text-muted hover:text-text text-xl">&times;</button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">

                    {/* Section 1: Venue Selection */}
                    <section>
                        <h3 className="text-sm font-bold text-accent-2 uppercase tracking-wider mb-3">1. 选择会议 (Venue)</h3>
                        <div className="bg-white/5 border border-border rounded-lg p-4 space-y-4">
                            <div className="flex gap-6 mb-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" checked={venueMode === 'hotpick'} onChange={() => setVenueMode('hotpick')} className="accent-accent" />
                                    <span>热门会议快捷选择</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" checked={venueMode === 'custom'} onChange={() => setVenueMode('custom')} className="accent-accent" />
                                    <span>自定义 Venue ID</span>
                                </label>
                            </div>

                            {venueMode === 'hotpick' ? (
                                <div className="grid grid-cols-3 gap-3">
                                    <div>
                                        <label className="block text-xs text-muted mb-1">会议</label>
                                        <select
                                            value={hotpickConf} onChange={e => setHotpickConf(e.target.value)}
                                            className="w-full bg-black/40 border border-border rounded px-3 py-2 text-text outline-none focus:border-accent"
                                        >
                                            {['NeurIPS', 'ICLR', 'ICML', 'CoRL', 'COLM', 'CVPR', 'ICCV'].map(c => <option key={c} value={c} className="bg-panel text-text">{c}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs text-muted mb-1">年份</label>
                                        <select
                                            value={hotpickYear} onChange={e => setHotpickYear(e.target.value)}
                                            className="w-full bg-black/40 border border-border rounded px-3 py-2 text-text outline-none focus:border-accent"
                                        >
                                            {[2025, 2024, 2023, 2022, 2021, 2020, 2019].map(y => <option key={y} value={y} className="bg-panel text-text">{y}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs text-muted mb-1">Track</label>
                                        <input
                                            value={hotpickTrack} onChange={e => setHotpickTrack(e.target.value)}
                                            className="w-full bg-black/40 border border-border rounded px-3 py-2 text-text outline-none focus:border-accent"
                                        />
                                    </div>
                                </div>
                            ) : (
                                <div>
                                    <input
                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-text outline-none focus:border-accent font-mono text-sm"
                                        placeholder="例如: NeurIPS.cc/2024/Conference"
                                        value={customVenueId} onChange={e => setCustomVenueId(e.target.value)}
                                    />
                                </div>
                            )}

                            <div className="text-xs text-muted font-mono bg-black/40 p-2 rounded">
                                Preview: {getVenueId()}
                            </div>
                        </div>
                    </section>

                    {/* Section 2: Scope */}
                    <section>
                        <h3 className="text-sm font-bold text-accent-2 uppercase tracking-wider mb-3">2. 抓取范围 (Scope)</h3>
                        <div className="bg-white/5 border border-border rounded-lg p-4 space-y-4">
                            <div className="flex flex-col gap-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={fetchAllAc}
                                        onChange={e => setFetchAllAc(e.target.checked)}
                                        className="accent-accent w-4 h-4"
                                    />
                                    <span className="font-medium text-accent-2">🚀 抓取全部 Accept 论文 (Fetch All)</span>
                                </label>
                                <p className="text-xs text-muted pl-6">开启后将忽略数量限制，自动抓取该会议所有接收论文。</p>
                            </div>

                            {!fetchAllAc && (
                                <div className="space-y-4 pl-6 border-l-2 border-border/30">
                                    <div className="flex gap-6">
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input type="radio" checked={fetchScope === 'accepted_only'} onChange={() => setFetchScope('accepted_only')} className="accent-accent" />
                                            <span>仅 Accept</span>
                                        </label>
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input type="radio" checked={fetchScope === 'all'} onChange={() => setFetchScope('all')} className="accent-accent" />
                                            <span>全部 (含 Reject/Pending)</span>
                                        </label>
                                    </div>

                                    <div>
                                        <label className="block text-xs text-muted mb-1">数量上限 (Limit)</label>
                                        <input
                                            type="number" min="10" max="1000" step="10"
                                            value={limit} onChange={e => setLimit(e.target.value)}
                                            className="w-32 bg-black/40 border border-border rounded px-2 py-1 text-text outline-none focus:border-accent"
                                        />
                                    </div>
                                </div>
                            )}

                            <label className="flex items-center gap-2 cursor-pointer pt-2 border-t border-border/30">
                                <input type="checkbox" checked={skipExisting} onChange={e => setSkipExisting(e.target.checked)} className="accent-accent" />
                                <span className="text-sm">追加抓取 (跳过已存在论文)</span>
                            </label>
                        </div>
                    </section>

                    {/* Section 3: PDF Options */}
                    <section>
                        <h3 className="text-sm font-bold text-accent-2 uppercase tracking-wider mb-3">3. PDF 处理 (Options)</h3>
                        <div className="bg-white/5 border border-border rounded-lg p-4 grid grid-cols-2 gap-6">
                            <div className="space-y-3">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input type="checkbox" checked={downloadPdf} onChange={e => setDownloadPdf(e.target.checked)} className="accent-accent" />
                                    <span>下载 PDF</span>
                                </label>
                                <label className={`flex items-center gap-2 cursor-pointer ${!downloadPdf ? 'opacity-50 pointer-events-none' : ''}`}>
                                    <input type="checkbox" checked={parsePdf} onChange={e => setParsePdf(e.target.checked)} className="accent-accent" />
                                    <span>解析 PDF 全文</span>
                                </label>
                            </div>

                            <div className={`${!parsePdf ? 'opacity-50' : ''}`}>
                                <label className="block text-xs text-muted mb-1">最大解析页数: {maxPages}</label>
                                <input
                                    type="range" min="1" max="50"
                                    value={maxPages} onChange={e => setMaxPages(e.target.value)}
                                    className="w-full accent-accent"
                                    disabled={!parsePdf}
                                />
                                <p className="text-xs text-muted mt-1">建议 8-12 页。页数越多解析越慢。</p>
                            </div>
                        </div>
                    </section>

                    {/* Progress Display */}
                    {(status || jobProgress) && (
                        <div className="space-y-4 p-4 bg-panel-2 border border-border rounded-lg">
                            <div className="flex items-center gap-3">
                                {loading && (
                                    <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                                )}
                                {jobProgress?.status === 'done' && (
                                    <div className="text-green-500">✓</div>
                                )}
                                {jobProgress?.status === 'error' && (
                                    <div className="text-red-500">✗</div>
                                )}
                                <span className="text-sm font-mono text-accent-2">{status}</span>
                            </div>

                            {/* Progress bars for each stage */}
                            {jobProgress?.progress && (
                                <div className="space-y-3">
                                    {jobProgress.progress.fetch_papers && (
                                        <ProgressBar
                                            label="📄 获取论文元数据"
                                            current={jobProgress.progress.fetch_papers.current || 0}
                                            total={jobProgress.progress.fetch_papers.total || 0}
                                            stage="fetch_papers"
                                        />
                                    )}
                                    {jobProgress.progress.download_pdf && (
                                        <ProgressBar
                                            label="📥 下载 PDF"
                                            current={jobProgress.progress.download_pdf.current || 0}
                                            total={jobProgress.progress.download_pdf.total || 0}
                                            stage="download_pdf"
                                        />
                                    )}
                                    {jobProgress.progress.parse_pdf && (
                                        <ProgressBar
                                            label="🔍 解析 PDF"
                                            current={jobProgress.progress.parse_pdf.current || 0}
                                            total={jobProgress.progress.parse_pdf.total || 0}
                                            stage="parse_pdf"
                                        />
                                    )}
                                    {jobProgress.progress.embedding && (
                                        <ProgressBar
                                            label="🧠 生成 Embedding"
                                            current={jobProgress.progress.embedding.current || 0}
                                            total={jobProgress.progress.embedding.total || 0}
                                            stage="embedding"
                                        />
                                    )}
                                </div>
                            )}

                            {jobProgress?.error && (
                                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
                                    {jobProgress.error}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="p-5 border-t border-border bg-panel-2 flex justify-end gap-3">
                    <button onClick={onClose} className="px-5 py-2 rounded-lg text-muted hover:text-text hover:bg-white/5 transition-colors">
                        取消
                    </button>
                    <button
                        onClick={handleRun} disabled={loading}
                        className="px-6 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-accent/40 transition-all font-medium"
                    >
                        {loading ? '启动中...' : '开始导入'}
                    </button>
                </div>
            </motion.div>
        </div>
    );
}
