import React, { useEffect, useState } from 'react';
import { MarkdownRenderer, slugify } from './MarkdownRenderer';
import { Download, ChevronRight, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';

const extractHeadings = (markdown) => {
    if (!markdown) return [];
    const lines = markdown.split('\n');
    const headings = [];
    lines.forEach(line => {
        // Match # Title, ## Title etc.
        const match = line.match(/^(#{1,3})\s+(.*)$/);
        if (match) {
            headings.push({
                level: match[1].length,
                text: match[2].trim(),
                id: slugify(match[2].trim())
            });
        }
    });
    return headings;
};

export function ReportView({ report, verificationResult, onCitationClick }) {
    const [headings, setHeadings] = useState([]);
    const [activeId, setActiveId] = useState('');

    // SAFETY: Log data status
    console.log('[ReportView] Rendering with:', {
        reportType: typeof report,
        reportLength: report?.length,
        hasVerification: !!verificationResult
    });

    // All Hooks must be called BEFORE any early returns
    useEffect(() => {
        if (report) {
            setHeadings(extractHeadings(report));
        }
    }, [report]);

    // Active link highlighting on scroll
    useEffect(() => {
        if (!report || headings.length === 0) return;

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setActiveId(entry.target.id);
                    }
                });
            },
            { rootMargin: '-10% 0px -80% 0px' }
        );

        headings.forEach(({ id }) => {
            const el = document.getElementById(id);
            if (el) observer.observe(el);
        });

        return () => observer.disconnect();
    }, [headings, report]);

    // Now we can do early return AFTER all hooks
    if (!report) {
        return (
            <div className="flex items-center justify-center h-full bg-panel-2 rounded-xl border border-border">
                <div className="text-center p-8">
                    <h2 className="text-2xl font-bold text-red-400 mb-4">报告数据缺失</h2>
                    <p className="text-muted">后端未返回有效的报告内容。请检查控制台日志。</p>
                </div>
            </div>
        );
    }

    const handleDownload = () => {
        const blob = new Blob([report], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `MUJICA_Report_${Date.now()}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };

    return (
        <div className="flex flex-col md:flex-row h-full overflow-hidden bg-panel-2 rounded-xl border border-border mt-4">
            {/* Sidebar TOC - Hidden on mobile */}
            <div className="hidden md:flex w-64 flex-col border-r border-border bg-panel/50 backdrop-blur-sm">
                <div className="p-4 border-b border-border">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-muted flex items-center gap-2">
                        <ChevronRight size={14} /> 目录导航
                    </h3>
                </div>
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                    <nav className="space-y-1">
                        {headings.map((h, i) => (
                            <a
                                key={i}
                                href={`#${h.id}`}
                                onClick={(e) => {
                                    e.preventDefault();
                                    document.getElementById(h.id)?.scrollIntoView({ behavior: 'smooth' });
                                }}
                                className={`block text-sm py-1.5 px-3 rounded-md transition-all duration-200 truncate border-l-2
                                    ${activeId === h.id
                                        ? 'bg-accent/10 text-accent border-accent font-medium'
                                        : 'text-muted hover:text-foreground hover:bg-white/5 border-transparent'
                                    }
                                    ${h.level === 1 ? '' : h.level === 2 ? 'ml-2' : 'ml-4'}
                                `}
                            >
                                {h.text}
                            </a>
                        ))}
                    </nav>
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 overflow-y-auto custom-scrollbar relative bg-panel-2">
                <div className="w-full px-6 py-10 min-h-full">
                    {/* Header Actions */}
                    <div className="max-w-4xl mx-auto">
                        <div className="flex justify-between items-center mb-12 pb-6 border-b border-border">
                            <h1 className="text-4xl font-black text-accent-2 tracking-tight">最终报告</h1>
                            <button
                                onClick={handleDownload}
                                className="px-4 py-2 bg-accent/90 hover:bg-accent text-white rounded-lg flex items-center gap-2 text-sm font-medium transition-colors shadow-lg shadow-accent/20"
                            >
                                <Download size={16} /> 导出 Markdown
                            </button>
                        </div>

                        {/* Report Content - Narrower width */}
                        <div className="text-base leading-relaxed content-markdown fade-in-up text-gray-300">
                            <MarkdownRenderer content={report} onCitationClick={onCitationClick} />
                        </div>
                    </div>

                    {/* Verification Section - Enhanced Layout */}
                    {verificationResult && (
                        <div className="max-w-4xl mx-auto mt-20 pt-10 border-t border-border/50">
                            <h3 className="text-2xl font-bold mb-6 flex items-center gap-3 text-white">
                                <div className={`p-1 rounded ${verificationResult.score >= 7 ? 'bg-green-500/20 text-green-400' : verificationResult.score >= 4 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}`}>
                                    <CheckCircle size={24} />
                                </div>
                                验证报告
                            </h3>

                            {/* Score Display - Enhanced */}
                            <div className="bg-gradient-to-br from-black/30 to-black/10 p-8 rounded-2xl border border-white/10 backdrop-blur-sm mb-8">
                                <div className="flex items-center justify-between mb-6">
                                    <div>
                                        <div className="text-sm text-muted uppercase tracking-wider font-bold mb-1">信任评分</div>
                                        <div className="text-xs text-muted/70">基于对关键论点的验证</div>
                                    </div>
                                    <div className={`text-6xl font-black ${verificationResult.score >= 7 ? 'text-green-400' : verificationResult.score >= 4 ? 'text-yellow-400' : 'text-red-400'}`}>
                                        {verificationResult.score}<span className="text-2xl text-muted font-normal">/10</span>
                                    </div>
                                </div>

                                {/* Score Bar */}
                                <div className="h-3 bg-white/10 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full rounded-full transition-all duration-500 ${verificationResult.score >= 7 ? 'bg-gradient-to-r from-green-500 to-green-400' : verificationResult.score >= 4 ? 'bg-gradient-to-r from-yellow-500 to-yellow-400' : 'bg-gradient-to-r from-red-500 to-red-400'}`}
                                        style={{ width: `${(verificationResult.score / 10) * 100}%` }}
                                    />
                                </div>
                            </div>

                            {/* Detailed Comment - Rendered as Markdown with improved styling */}
                            <div className="bg-gradient-to-br from-black/30 to-black/10 p-8 rounded-2xl border border-white/10 backdrop-blur-sm">
                                <h4 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
                                    <AlertTriangle size={18} className="text-yellow-400" />
                                    详细核查结果
                                </h4>
                                <div className="verification-content prose prose-invert prose-sm max-w-none">
                                    <MarkdownRenderer content={verificationResult.comment || "暂无详细评语"} />
                                </div>
                            </div>

                            {/* Stats Grid */}
                            {verificationResult.stats && (
                                <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
                                    {verificationResult.stats.claims_checked !== undefined && (
                                        <div className="bg-white/5 p-5 rounded-xl text-center border border-white/5">
                                            <div className="text-3xl font-bold text-accent">{verificationResult.stats.claims_checked}</div>
                                            <div className="text-xs text-muted mt-1">论点检验数</div>
                                        </div>
                                    )}
                                    {verificationResult.stats.claims_total !== undefined && (
                                        <div className="bg-white/5 p-5 rounded-xl text-center border border-white/5">
                                            <div className="text-3xl font-bold text-blue-400">{verificationResult.stats.claims_total}</div>
                                            <div className="text-xs text-muted mt-1">论点总数</div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Bottom Padding */}
                    <div className="h-20"></div>
                </div>
            </div>
        </div>
    );
}
