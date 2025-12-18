import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

// Utility to generate IDs from text
export const slugify = (text) => {
    return text
        .toString()
        .toLowerCase()
        .trim()
        .replace(/\s+/g, '-')     // Replace spaces with -
        .replace(/[^\w\u4e00-\u9fa5-]+/g, '') // Remove all non-word chars (allow Chinese)
        .replace(/\-\-+/g, '-');  // Replace multiple - with single -
};

// Convert Unicode superscript back to R# for display
const superToNormal = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
};

// Regex to match Unicode superscript citations like ⁽ᴿ¹²⁾ or ⁽ᴿ¹,ᴿ²⁾
const SUPER_CIT_REGEX = /⁽([ᴿ⁰¹²³⁴⁵⁶⁷⁸⁹,]+)⁾/g;

// Process text to wrap citations in styled spans (CLICKABLE)
function processCitations(text, onCitationClick) {
    if (!text || typeof text !== 'string') return text;

    const parts = [];
    let lastIndex = 0;
    let match;

    const regex = new RegExp(SUPER_CIT_REGEX.source, 'g');

    while ((match = regex.exec(text)) !== null) {
        // Add text before match
        if (match.index > lastIndex) {
            parts.push(text.slice(lastIndex, match.index));
        }

        // Parse the citation content
        const citContent = match[1];
        // Convert back to readable format: ᴿ¹² -> R12
        let readable = citContent.replace(/ᴿ/g, 'R');
        for (const [sup, norm] of Object.entries(superToNormal)) {
            readable = readable.split(sup).join(norm);
        }

        // Extract individual refs (e.g., "R1,R2" -> ["R1", "R2"])
        const refs = readable.split(',').map(r => r.trim()).filter(Boolean);

        // Create clickable element
        parts.push(
            <span
                key={match.index}
                className="inline-flex items-center gap-0.5"
            >
                <span className="text-accent/60 text-[0.6em] align-super">⁽</span>
                {refs.map((ref, i) => (
                    <React.Fragment key={ref}>
                        {i > 0 && <span className="text-accent/60 text-[0.6em] align-super">,</span>}
                        <button
                            onClick={() => onCitationClick && onCitationClick(ref)}
                            className={`text-[0.7em] align-super font-medium transition-colors 
                                ${onCitationClick
                                    ? 'text-accent hover:text-accent-hover cursor-pointer hover:underline decoration-dotted underline-offset-2'
                                    : 'text-accent cursor-default'}`}
                            title={`查看来源: ${ref}`}
                        >
                            {ref}
                        </button>
                    </React.Fragment>
                ))}
                <span className="text-accent/60 text-[0.6em] align-super">⁾</span>
            </span>
        );

        lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
        parts.push(text.slice(lastIndex));
    }

    return parts.length > 0 ? parts : text;
}

export function MarkdownRenderer({ content, onCitationClick }) {
    const HeaderRenderer = ({ level, children }) => {
        // Extract text content from children
        const text = React.Children.toArray(children).reduce((acc, child) => {
            return acc + (typeof child === 'string' ? child : '');
        }, '');
        const id = slugify(text);
        const Tag = `h${level}`;

        return <Tag id={id}>{children}</Tag>;
    };

    // Custom text renderer to handle citations
    const TextRenderer = ({ children }) => {
        if (typeof children === 'string') {
            return <>{processCitations(children, onCitationClick)}</>;
        }
        return <>{children}</>;
    };

    return (
        <div className="max-w-none markdown-content">
            <ReactMarkdown
                components={{
                    h1: ({ node, ...props }) => <HeaderRenderer level={1} {...props} />,
                    h2: ({ node, ...props }) => <HeaderRenderer level={2} {...props} />,
                    h3: ({ node, ...props }) => <HeaderRenderer level={3} {...props} />,
                    // Process citations in paragraphs
                    p: ({ node, children, ...props }) => (
                        <p {...props}>
                            {React.Children.map(children, child =>
                                typeof child === 'string'
                                    ? processCitations(child, onCitationClick)
                                    : child
                            )}
                        </p>
                    ),
                    // Process citations in list items
                    li: ({ node, children, ...props }) => (
                        <li {...props}>
                            {React.Children.map(children, child =>
                                typeof child === 'string'
                                    ? processCitations(child, onCitationClick)
                                    : child
                            )}
                        </li>
                    ),
                    code({ node, inline, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '')
                        return !inline && match ? (
                            <SyntaxHighlighter
                                {...props}
                                style={vscDarkPlus}
                                language={match[1]}
                                PreTag="div"
                            >
                                {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                        ) : (
                            <code {...props} className={className}>
                                {children}
                            </code>
                        )
                    }
                }}
            >
                {content || ''}
            </ReactMarkdown>
        </div>
    );
}
