import React, { useState, useEffect } from 'react';
import { api } from '../api';
import { motion } from 'framer-motion';
import { Save, Eye, EyeOff } from 'lucide-react';

export function SettingsView({ onClose }) {
    const [config, setConfig] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [showKey, setShowKey] = useState({});
    const [saveStatus, setSaveStatus] = useState(null); // { type: 'success' | 'error', message: string }

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            const res = await api.getConfig();
            setConfig(res.data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        setSaveStatus(null);

        // Filter out _SET keys which are just indicators
        const toSave = {};
        for (const [k, v] of Object.entries(config)) {
            if (!k.endsWith('_SET') && v !== undefined) {
                toSave[k] = v;
            }
        }

        try {
            await api.updateConfig(toSave);
            await loadConfig(); // Reload to get mask states
            setSaveStatus({ type: 'success', message: '设置已保存！' });
            setTimeout(() => setSaveStatus(null), 3000);
        } catch (e) {
            setSaveStatus({ type: 'error', message: '保存失败: ' + e.message });
        } finally {
            setSaving(false);
        }
    };

    const handleChange = (key, val) => {
        setConfig(prev => ({ ...prev, [key]: val }));
    };

    const toggleShow = (key) => {
        setShowKey(prev => ({ ...prev, [key]: !prev[key] }));
    };

    if (loading) return <div className="p-8 text-center text-muted">Loading settings...</div>;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <motion.div
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-panel border border-border w-full max-w-2xl h-[80vh] flex flex-col rounded-xl shadow-2xl relative"
            >
                <div className="p-6 border-b border-border flex justify-between items-center bg-panel-2 rounded-t-xl">
                    <h2 className="text-2xl font-bold">系统设置</h2>
                    <button onClick={onClose} className="text-muted hover:text-text text-xl">&times;</button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">

                    {/* Chat Config */}
                    <Section title="对话 & 大模型">
                        <Field
                            label="OpenAI 接口地址 (Base URL)"
                            value={config.OPENAI_BASE_URL || ''}
                            onChange={v => handleChange('OPENAI_BASE_URL', v)}
                            placeholder="https://api.openai.com/v1"
                        />
                        <Field
                            label="OpenAI API 密钥 (API Key)"
                            type={showKey.chat ? 'text' : 'password'}
                            value={config.OPENAI_API_KEY || ''}
                            onChange={v => handleChange('OPENAI_API_KEY', v)}
                            placeholder={config.OPENAI_API_KEY_SET ? '******** (已通过环境变量设置)' : 'sk-...'}
                            rightIcon={
                                <button onClick={() => toggleShow('chat')} className="p-2 text-muted hover:text-text">
                                    {showKey.chat ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            }
                        />
                        <Field
                            label="默认模型"
                            value={config.MUJICA_DEFAULT_MODEL || ''}
                            onChange={v => handleChange('MUJICA_DEFAULT_MODEL', v)}
                            placeholder="gpt-4o"
                        />
                    </Section>

                    {/* Embedding Config */}
                    <Section title="Embedding & 知识库">
                        <Field
                            label="Embedding 模型"
                            value={config.MUJICA_EMBEDDING_MODEL || ''}
                            onChange={v => handleChange('MUJICA_EMBEDDING_MODEL', v)}
                            placeholder="text-embedding-3-small"
                        />
                        <Field
                            label="Embedding 接口地址"
                            value={config.MUJICA_EMBEDDING_BASE_URL || ''}
                            onChange={v => handleChange('MUJICA_EMBEDDING_BASE_URL', v)}
                            placeholder="(可选) 如为空则使用对话接口地址"
                        />
                        <Field
                            label="Embedding API 密钥"
                            type={showKey.embed ? 'text' : 'password'}
                            value={config.MUJICA_EMBEDDING_API_KEY || ''}
                            onChange={v => handleChange('MUJICA_EMBEDDING_API_KEY', v)}
                            placeholder={config.MUJICA_EMBEDDING_API_KEY_SET ? '******** (已通过环境变量设置)' : 'sk-...'}
                            rightIcon={
                                <button onClick={() => toggleShow('embed')} className="p-2 text-muted hover:text-text">
                                    {showKey.embed ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            }
                        />
                    </Section>

                    {/* OpenReview */}
                    <Section title="OpenReview 凭证">
                        <div className="grid grid-cols-2 gap-4">
                            <Field
                                label="用户名 (Email)"
                                value={config.OPENREVIEW_USERNAME || ''}
                                onChange={v => handleChange('OPENREVIEW_USERNAME', v)}
                                placeholder="user@example.com"
                            />
                            <Field
                                label="密码"
                                type="password"
                                value={config.OPENREVIEW_PASSWORD || ''}
                                onChange={v => handleChange('OPENREVIEW_PASSWORD', v)}
                                placeholder={config.OPENREVIEW_CREDENTIALS_SET ? '********' : ''}
                            />
                        </div>
                    </Section>

                    {/* Advanced */}
                    <Section title="高级设置 (Advanced)">
                        <div className="space-y-4">
                            <label className="flex items-center gap-3 cursor-pointer p-3 bg-white/5 rounded-lg border border-border hover:border-accent transition-colors">
                                <input
                                    type="checkbox"
                                    className="accent-accent w-4 h-4"
                                    checked={config.MUJICA_FAKE_EMBEDDINGS === '1'}
                                    onChange={e => handleChange('MUJICA_FAKE_EMBEDDINGS', e.target.checked ? '1' : '0')}
                                />
                                <div>
                                    <div className="font-medium text-text">离线 Embedding (Fake)</div>
                                    <div className="text-xs text-muted">仅用于本地跑通流程，不调用 Embedding API（检索质量较差）。</div>
                                </div>
                            </label>

                            <label className="flex items-center gap-3 cursor-pointer p-3 bg-white/5 rounded-lg border border-border hover:border-accent transition-colors">
                                <input
                                    type="checkbox"
                                    className="accent-accent w-4 h-4"
                                    checked={config.MUJICA_DISABLE_JSON_MODE === '1'}
                                    onChange={e => handleChange('MUJICA_DISABLE_JSON_MODE', e.target.checked ? '1' : '0')}
                                />
                                <div>
                                    <div className="font-medium text-text">兼容模式：关闭 JSON Mode</div>
                                    <div className="text-xs text-muted">部分 OpenAI 兼容模型（如 GLM-4）不支持 response_format，开启此项可避免报错。</div>
                                </div>
                            </label>
                        </div>
                    </Section>

                </div>

                <div className="p-6 border-t border-border bg-panel-2 rounded-b-xl flex justify-between items-center gap-3">
                    {saveStatus ? (
                        <div className={`text-sm px-4 py-2 rounded-lg ${saveStatus.type === 'success' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                            {saveStatus.message}
                        </div>
                    ) : <div />}
                    <div className="flex gap-3">
                        <button onClick={onClose} className="px-6 py-2 rounded-lg text-muted hover:text-text">取消</button>
                        <button
                            onClick={handleSave} disabled={saving}
                            className="flex items-center gap-2 px-6 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-50 font-medium"
                        >
                            <Save size={18} /> {saving ? '保存中...' : '保存设置'}
                        </button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <div className="space-y-4">
            <h3 className="text-lg font-semibold text-accent-2 border-b border-border/50 pb-2">{title}</h3>
            <div className="space-y-4 pl-1">
                {children}
            </div>
        </div>
    );
}

function Field({ label, value, onChange, placeholder, type = 'text', rightIcon }) {
    return (
        <div>
            <label className="block text-sm font-medium text-muted mb-1.5">{label}</label>
            <div className="relative flex items-center">
                <input
                    type={type}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="w-full bg-black/40 border border-border rounded-lg px-4 py-2.5 text-text outline-none focus:border-accent transition-colors"
                />
                {rightIcon && <div className="absolute right-2">{rightIcon}</div>}
            </div>
        </div>
    );
}
