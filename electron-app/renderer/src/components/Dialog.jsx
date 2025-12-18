import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, CheckCircle, XCircle, Info } from 'lucide-react';

/**
 * 通用确认/提示对话框组件
 * 用于替代原生的 alert() 和 confirm()
 */
export function ConfirmDialog({
    open,
    onClose,
    onConfirm,
    title = "确认",
    message,
    confirmText = "确定",
    cancelText = "取消",
    type = "confirm", // 'confirm' | 'alert' | 'success' | 'error'
    danger = false,
}) {
    if (!open) return null;

    const icons = {
        confirm: <AlertCircle className="text-yellow-400" size={24} />,
        alert: <Info className="text-blue-400" size={24} />,
        success: <CheckCircle className="text-green-400" size={24} />,
        error: <XCircle className="text-red-400" size={24} />,
    };

    const handleConfirm = () => {
        if (onConfirm) onConfirm();
        onClose();
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-panel border border-border rounded-xl shadow-2xl max-w-md w-full mx-4"
            >
                <div className="p-6">
                    <div className="flex items-start gap-4">
                        <div className="flex-shrink-0 mt-0.5">
                            {icons[type]}
                        </div>
                        <div className="flex-1">
                            <h3 className="text-lg font-semibold text-text mb-2">{title}</h3>
                            <p className="text-muted text-sm whitespace-pre-line">{message}</p>
                        </div>
                    </div>
                </div>
                <div className="flex justify-end gap-3 p-4 border-t border-border bg-panel-2 rounded-b-xl">
                    {type === 'confirm' && (
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-muted hover:text-text rounded-lg transition-colors"
                        >
                            {cancelText}
                        </button>
                    )}
                    <button
                        onClick={handleConfirm}
                        className={`px-4 py-2 rounded-lg font-medium transition-all ${danger
                                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/50'
                                : 'bg-accent text-white hover:bg-accent-hover'
                            }`}
                    >
                        {confirmText}
                    </button>
                </div>
            </motion.div>
        </div>
    );
}

/**
 * Toast 通知组件
 * 用于显示临时消息
 */
export function Toast({ open, message, type = 'info', onClose }) {
    React.useEffect(() => {
        if (open) {
            const timer = setTimeout(onClose, 3000);
            return () => clearTimeout(timer);
        }
    }, [open, onClose]);

    if (!open) return null;

    const colors = {
        info: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
        success: 'bg-green-500/20 text-green-400 border-green-500/50',
        error: 'bg-red-500/20 text-red-400 border-red-500/50',
        warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className={`fixed top-4 right-4 z-[100] px-4 py-3 rounded-lg border shadow-lg ${colors[type]}`}
        >
            {message}
        </motion.div>
    );
}

/**
 * useConfirm hook - 简化确认对话框的使用
 */
export function useConfirm() {
    const [state, setState] = React.useState({
        open: false,
        title: '',
        message: '',
        type: 'confirm',
        danger: false,
        resolve: null,
    });

    const confirm = React.useCallback(({ title, message, danger = false }) => {
        return new Promise((resolve) => {
            setState({
                open: true,
                title,
                message,
                type: 'confirm',
                danger,
                resolve,
            });
        });
    }, []);

    const handleClose = React.useCallback(() => {
        state.resolve?.(false);
        setState(s => ({ ...s, open: false }));
    }, [state.resolve]);

    const handleConfirm = React.useCallback(() => {
        state.resolve?.(true);
        setState(s => ({ ...s, open: false }));
    }, [state.resolve]);

    const dialog = (
        <ConfirmDialog
            open={state.open}
            onClose={handleClose}
            onConfirm={handleConfirm}
            title={state.title}
            message={state.message}
            type={state.type}
            danger={state.danger}
        />
    );

    return { confirm, dialog };
}

/**
 * useToast hook - 简化 toast 通知的使用
 */
export function useToast() {
    const [state, setState] = React.useState({
        open: false,
        message: '',
        type: 'info',
    });

    const show = React.useCallback((message, type = 'info') => {
        setState({ open: true, message, type });
    }, []);

    const close = React.useCallback(() => {
        setState(s => ({ ...s, open: false }));
    }, []);

    const toast = (
        <AnimatePresence>
            {state.open && (
                <Toast
                    open={state.open}
                    message={state.message}
                    type={state.type}
                    onClose={close}
                />
            )}
        </AnimatePresence>
    );

    return { show, toast };
}
