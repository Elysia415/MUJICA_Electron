import React from 'react';
import { cn } from '../lib/utils';
import { Loader2, CheckCircle2, XCircle, FileText, Search, PenTool } from 'lucide-react';
import { motion } from 'framer-motion';

export function JobStatus({ job }) {
    if (!job) return null;

    const { status, stage, message, progress } = job;

    const getIcon = () => {
        if (status === 'error') return <XCircle className="text-red-500" />;
        if (status === 'done') return <CheckCircle2 className="text-green-500" />;
        return <Loader2 className="animate-spin text-accent-2" />;
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-panel border border-border rounded-lg p-4 shadow-lg backdrop-blur-md"
        >
            <div className="flex items-center gap-3 mb-2">
                {getIcon()}
                <h3 className="font-semibold text-lg text-text capitalize">{status === 'running' ? stage : status}</h3>
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
