import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { FileText, Trash2, Clock, Edit2, Check, X } from 'lucide-react';
import { motion } from 'framer-motion';

export function HistoryView({ onLoad }) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            const res = await api.listHistory();
            // res.data.conversations is list of [id, title, ts]
            setHistory(res.data.conversations);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleLoad = async (cid) => {
        try {
            const res = await api.getHistory(cid);
            onLoad(res.data); // data is the full session state
        } catch (e) {
            alert('Failed to load history: ' + e.message);
        }
    };

    const handleDelete = async (e, cid) => {
        e.stopPropagation();
        if (!confirm('确定删除此对话吗？')) return;
        try {
            await api.deleteHistory(cid);
            loadHistory();
        } catch (err) {
            alert('删除失败');
        }
    };

    const [editingId, setEditingId] = useState(null);
    const [editTitle, setEditTitle] = useState('');

    const startEdit = (e, cid, currentTitle) => {
        e.stopPropagation();
        setEditingId(cid);
        setEditTitle(currentTitle || '');
    };

    const handleRename = async (e) => {
        e.stopPropagation();
        try {
            await api.renameHistory(editingId, editTitle);
            setEditingId(null);
            loadHistory();
        } catch (err) {
            alert('重命名失败: ' + err.message);
        }
    };

    return (
        <div className="h-full flex flex-col p-6 max-w-4xl mx-auto w-full">
            <h1 className="text-3xl font-bold text-accent-2 mb-6">调研历史</h1>

            {loading && <div className="text-muted">加载历史中...</div>}

            <div className="grid gap-4">
                {history.map(([cid, title, ts]) => (
                    <motion.div
                        key={cid}
                        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                        onClick={() => handleLoad(cid)}
                        className="group bg-panel border border-border p-4 rounded-xl cursor-pointer hover:border-accent transition-all hover:bg-white/5 flex items-center justify-between"
                    >
                        <div className="flex items-center gap-4 flex-1">
                            <div className="p-3 bg-accent/20 rounded-lg text-accent-2 shrink-0">
                                <FileText size={24} />
                            </div>

                            {editingId === cid ? (
                                <div className="flex items-center gap-2 flex-1 mr-4" onClick={e => e.stopPropagation()}>
                                    <input
                                        value={editTitle}
                                        onChange={e => setEditTitle(e.target.value)}
                                        className="bg-black/40 border border-accent rounded px-2 py-1 text-text outline-none flex-1"
                                        autoFocus
                                        onKeyDown={e => { if (e.key === 'Enter') handleRename(e); }}
                                    />
                                    <button onClick={handleRename} className="p-1 text-green-400 hover:bg-green-500/10 rounded"><Check size={16} /></button>
                                    <button onClick={(e) => { e.stopPropagation(); setEditingId(null) }} className="p-1 text-muted hover:bg-white/10 rounded"><X size={16} /></button>
                                </div>
                            ) : (
                                <div>
                                    <div className="flex items-center gap-2 group-hover:gap-3 transition-all">
                                        <h3 className="font-bold text-lg text-text group-hover:text-accent-2 transition-colors line-clamp-1">
                                            {title || '未命名调研'}
                                        </h3>
                                        <button
                                            onClick={(e) => startEdit(e, cid, title)}
                                            className="opacity-0 group-hover:opacity-100 p-1 text-muted hover:text-accent transition-opacity"
                                            title="Rename"
                                        >
                                            <Edit2 size={14} />
                                        </button>
                                    </div>
                                    <div className="text-sm text-muted flex items-center gap-2">
                                        <Clock size={12} /> {new Date(ts * 1000).toLocaleString()}
                                        <span className="font-mono text-xs opacity-50">ID: {cid.substring(0, 8)}</span>
                                    </div>
                                </div>
                            )}
                        </div>

                        <button
                            onClick={(e) => handleDelete(e, cid)}
                            className="p-2 text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                            <Trash2 size={18} />
                        </button>
                    </motion.div>
                ))}

                {!loading && history.length === 0 && (
                    <div className="text-center text-muted p-10 border border-border border-dashed rounded-xl">
                        暂无历史记录。开始新的调研吧！
                    </div>
                )}
            </div>
        </div>
    );
}
