import React from 'react';
import { api } from '../api';
import { cn } from '../lib/utils';
import { Loader2, CheckCircle2, XCircle, FileText, Search, PenTool, StopCircle } from 'lucide-react';
import { motion } from 'framer-motion';

export function JobStatus({ job, onCancel }) {
    if (!job) return null;

    const { status, stage, message, progress, job_id } = job;

    const handleCancel = async () => {
        if (!job_id) return;
        try {
            await api.cancelJob(job_id);
            onCancel?.();
        } catch (e) {
            console.error('Cancel failed:', e);
        }
    };

    const getIcon = () => {
        if (status === 'error') return <XCircle className="text-red-500" />;
        if (status === 'done') return <CheckCircle2 className="text-green-500" />;
        if (status === 'cancelled') return <StopCircle className="text-yellow-500" />;
        return <Loader2 className="animate-spin text-accent-2" />;
    };

    const getStatusText = () => {
        if (status === 'error') return '出错了';
        if (status === 'done') return '完成';
        if (status === 'cancelled') return '已取消';
        if (status === 'running') {
            if (stage === 'plan') return '规划中...';
            if (stage === 'research') return '调研中...';
            if (stage === 'write') return '撰写报告中...';
            if (stage === 'verify') return '验证中...';
            return '进行中...';
        }
        return status;
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-panel border border-border rounded-lg p-4 shadow-lg backdrop-blur-md"
        >
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                    {getIcon()}
                    <h3 className="font-semibold text-lg text-text capitalize">{getStatusText()}</h3>
                </div>
                {status === 'running' && (
                    <button
                        onClick={handleCancel}
                        className="flex items-center gap-1 px-3 py-1 text-sm text-red-400 hover:bg-red-500/20 rounded transition-colors"
                    >
                        <StopCircle size={14} /> 取消
                    </button>
                )}
            </div>
            <p className="text-muted text-sm font-mono">{message}</p>

            {/* Detailed Progress Bars based on Stage */}
            {stage === 'write' && (
                <div className="mt-2 h-1 bg-gray-800 rounded-full overflow-hidden">
                    <motion.div
                        className="h-full bg-accent"
                        initial={{ width: 0 }}
                        animate={{ width: job.result?.final_report ? "100%" : "50%" }}
                    />
                </div>
            )}
        </motion.div>
    );
}

