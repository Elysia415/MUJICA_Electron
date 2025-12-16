import React, { useState, useEffect } from 'react';
import { Plus, Trash2, ChevronDown, ChevronUp, Code, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * PlanEditor - Editable form view for research plan (mirrors Streamlit's plan editor)
 * @param {object} plan - The initial plan object
 * @param {function} onUpdate - Callback when plan is updated
 * @param {function} onApprove - Callback when user approves the plan
 */
export function PlanEditor({ plan, onUpdate, onApprove }) {
    const [title, setTitle] = useState(plan?.title || '');
    const [sections, setSections] = useState(plan?.sections || []);
    const [estimatedPapers, setEstimatedPapers] = useState(plan?.estimated_papers || 0);
    const [expandedSections, setExpandedSections] = useState({});
    const [editorMode, setEditorMode] = useState('form'); // 'form' | 'json'
    const [jsonText, setJsonText] = useState('');
    const [jsonError, setJsonError] = useState('');

    // Sync with external plan changes
    useEffect(() => {
        if (plan) {
            setTitle(plan.title || '');
            setSections(plan.sections || []);
            setEstimatedPapers(plan.estimated_papers || 0);
        }
    }, [plan]);

    // Calculate estimated papers from top_k sum
    useEffect(() => {
        const sum = sections.reduce((acc, s) => acc + (s.top_k_papers || 5), 0);
        setEstimatedPapers(sum);
    }, [sections]);

    const buildPlan = () => ({
        title: title || 'Research Plan',
        sections: sections,
        estimated_papers: estimatedPapers
    });

    const handleSectionChange = (idx, field, value) => {
        const newSections = [...sections];
        if (field.startsWith('filters.')) {
            const filterKey = field.split('.')[1];
            newSections[idx] = {
                ...newSections[idx],
                filters: { ...newSections[idx].filters, [filterKey]: value }
            };
        } else {
            newSections[idx] = { ...newSections[idx], [field]: value };
        }
        setSections(newSections);
        onUpdate?.(buildPlan());
    };

    const addSection = () => {
        setSections([...sections, { name: 'New Section', search_query: '', filters: {}, top_k_papers: 5 }]);
    };

    const deleteSection = (idx) => {
        setSections(sections.filter((_, i) => i !== idx));
    };

    const toggleExpand = (idx) => {
        setExpandedSections(prev => ({ ...prev, [idx]: !prev[idx] }));
    };

    // JSON mode sync
    useEffect(() => {
        if (editorMode === 'json') {
            setJsonText(JSON.stringify(buildPlan(), null, 2));
            setJsonError('');
        }
    }, [editorMode]);

    const applyJson = () => {
        try {
            const parsed = JSON.parse(jsonText);
            setTitle(parsed.title || '');
            setSections(parsed.sections || []);
            setJsonError('');
            onUpdate?.(parsed);
        } catch (e) {
            setJsonError('JSON 格式错误: ' + e.message);
        }
    };

    return (
        <div className="space-y-6">
            {/* Mode Toggle */}
            <div className="flex gap-2 justify-end">
                <button
                    onClick={() => setEditorMode('form')}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded text-sm transition-colors ${editorMode === 'form' ? 'bg-accent text-white' : 'bg-white/5 text-muted hover:text-text'}`}
                >
                    <FileText size={14} /> 可读版
                </button>
                <button
                    onClick={() => setEditorMode('json')}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded text-sm transition-colors ${editorMode === 'json' ? 'bg-accent text-white' : 'bg-white/5 text-muted hover:text-text'}`}
                >
                    <Code size={14} /> JSON
                </button>
            </div>

            {editorMode === 'json' ? (
                /* JSON Editor Mode */
                <div className="space-y-4">
                    <textarea
                        value={jsonText}
                        onChange={e => setJsonText(e.target.value)}
                        className="w-full h-96 bg-black/40 border border-border rounded-lg px-4 py-3 text-text font-mono text-sm outline-none focus:border-accent"
                        placeholder='{"title": "...", "sections": [...]}'
                    />
                    {jsonError && <div className="text-red-400 text-sm">{jsonError}</div>}
                    <div className="flex gap-2">
                        <button onClick={applyJson} className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover">
                            应用 JSON
                        </button>
                        <button onClick={() => setJsonText(JSON.stringify(buildPlan(), null, 2))} className="px-4 py-2 bg-white/5 text-muted rounded hover:text-text">
                            重置
                        </button>
                    </div>
                </div>
            ) : (
                /* Form Editor Mode */
                <>
                    {/* Title */}
                    <div>
                        <label className="block text-sm font-medium text-muted mb-1">报告标题</label>
                        <input
                            className="w-full bg-black/40 border border-border rounded-lg px-4 py-2.5 text-text outline-none focus:border-accent"
                            value={title}
                            onChange={e => setTitle(e.target.value)}
                            placeholder="输入报告标题..."
                        />
                    </div>

                    {/* Sections */}
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <h3 className="text-lg font-semibold text-accent-2">章节 ({sections.length})</h3>
                            <button
                                onClick={addSection}
                                className="flex items-center gap-1 text-sm text-accent hover:text-accent-2 transition-colors"
                            >
                                <Plus size={16} /> 添加章节
                            </button>
                        </div>

                        <AnimatePresence>
                            {sections.map((section, idx) => (
                                <motion.div
                                    key={idx}
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className="bg-white/5 border border-border rounded-lg overflow-hidden"
                                >
                                    {/* Section Header */}
                                    <div
                                        className="flex items-center justify-between p-4 cursor-pointer hover:bg-white/5"
                                        onClick={() => toggleExpand(idx)}
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className="w-6 h-6 flex items-center justify-center bg-accent/20 rounded text-accent-2 text-sm font-bold">
                                                {idx + 1}
                                            </span>
                                            <input
                                                className="bg-transparent border-none outline-none text-text font-medium"
                                                value={section.name}
                                                onChange={e => handleSectionChange(idx, 'name', e.target.value)}
                                                onClick={e => e.stopPropagation()}
                                                placeholder="章节名称"
                                            />
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={(e) => { e.stopPropagation(); deleteSection(idx); }}
                                                className="p-1.5 text-red-400 hover:bg-red-500/20 rounded"
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                            {expandedSections[idx] ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                                        </div>
                                    </div>

                                    {/* Section Details (Expanded) */}
                                    {expandedSections[idx] && (
                                        <div className="p-4 pt-0 space-y-4 border-t border-border/50">
                                            {/* Search Query */}
                                            <div>
                                                <label className="block text-xs text-muted mb-1">搜索关键词</label>
                                                <input
                                                    className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                    value={section.search_query || ''}
                                                    onChange={e => handleSectionChange(idx, 'search_query', e.target.value)}
                                                    placeholder="例如：reinforcement learning from human feedback"
                                                />
                                            </div>

                                            {/* Top K */}
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">引用数量 (Top K)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.top_k_papers || 5}
                                                        onChange={e => handleSectionChange(idx, 'top_k_papers', parseInt(e.target.value) || 5)}
                                                        min={1}
                                                        max={50}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">最低评分</label>
                                                    <input
                                                        type="number"
                                                        step="0.1"
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.min_rating || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.min_rating', parseFloat(e.target.value) || null)}
                                                        placeholder="例如：7.5"
                                                    />
                                                </div>
                                            </div>

                                            {/* Filters */}
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">包含会议/期刊</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.venue_contains || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.venue_contains', e.target.value)}
                                                        placeholder="例如：ICLR"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">年份</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.year_in?.join(', ') || ''}
                                                        onChange={e => {
                                                            const years = e.target.value.split(/[,\s]+/).map(y => parseInt(y.trim())).filter(y => !isNaN(y));
                                                            handleSectionChange(idx, 'filters.year_in', years.length ? years : null);
                                                        }}
                                                        placeholder="例如：2023, 2024"
                                                    />
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">标题包含</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.title_contains || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.title_contains', e.target.value)}
                                                        placeholder="论文标题关键词"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">作者包含</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.author_contains || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.author_contains', e.target.value)}
                                                        placeholder="例如：Bengio"
                                                    />
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">关键词包含 (Keywords)</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.keyword_contains || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.keyword_contains', e.target.value)}
                                                        placeholder="例如：LLM, Agent"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">决策类型 (Decision)</label>
                                                    <input
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.decision_in?.join(', ') || ''}
                                                        onChange={e => {
                                                            const vals = e.target.value.split(/[,\uff0c]+/).map(s => s.trim()).filter(s => s);
                                                            handleSectionChange(idx, 'filters.decision_in', vals.length ? vals : null);
                                                        }}
                                                        placeholder="Accept (oral), Accept (poster)..."
                                                    />
                                                </div>
                                            </div>

                                            <div>
                                                <label className="block text-xs text-muted mb-1">展示类型 (Presentation: oral/spotlight/poster)</label>
                                                <input
                                                    className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                    value={section.filters?.presentation_in?.join(', ') || ''}
                                                    onChange={e => {
                                                        const vals = e.target.value.split(/[,\uff0c]+/).map(s => s.trim().toLowerCase()).filter(s => s);
                                                        handleSectionChange(idx, 'filters.presentation_in', vals.length ? vals : null);
                                                    }}
                                                    placeholder="例如：oral, spotlight"
                                                />
                                            </div>

                                            {/* Year Range */}
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">最早年份 (min_year)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.min_year || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.min_year', parseInt(e.target.value) || null)}
                                                        placeholder="例如：2020"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-xs text-muted mb-1">最晚年份 (max_year)</label>
                                                    <input
                                                        type="number"
                                                        className="w-full bg-black/40 border border-border rounded px-3 py-2 text-sm text-text outline-none focus:border-accent"
                                                        value={section.filters?.max_year || ''}
                                                        onChange={e => handleSectionChange(idx, 'filters.max_year', parseInt(e.target.value) || null)}
                                                        placeholder="例如：2024"
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    </div>

                    {/* Summary */}
                    <div className="bg-accent/10 border border-accent/30 rounded-lg p-4 flex justify-between items-center">
                        <div>
                            <div className="text-sm text-muted">预计阅读论文数</div>
                            <div className="text-2xl font-bold text-accent-2">{estimatedPapers}</div>
                        </div>
                        <button
                            onClick={() => onApprove?.(buildPlan())}
                            className="px-6 py-3 bg-gradient-to-r from-accent to-[#5e001f] text-white font-bold rounded-lg shadow-lg hover:shadow-accent/50 transition-all"
                        >
                            ✓ 确认并开始调研
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

