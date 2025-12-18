import openreview
import os
import requests
import time
import re
import random
from typing import List, Dict, Optional, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class ConferenceDataFetcher:
    """
    从 OpenReview 获取会议论文数据
    支持获取论文元数据、评审意见、PDF 下载等
    """
    
    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = output_dir
        self.client = None
        self.pdf_dir = os.path.join(output_dir, "pdfs")
        
        # 创建输出目录
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.pdf_dir).mkdir(parents=True, exist_ok=True)
    
    def _init_client(self):
        """初始化 OpenReview 客户端"""
        if self.client is None:
            try:
                # 从环境变量获取认证信息（可选）
                username = os.getenv('OPENREVIEW_USERNAME')
                password = os.getenv('OPENREVIEW_PASSWORD')
                
                self.client = openreview.api.OpenReviewClient(
                    baseurl='https://api2.openreview.net',
                    username=username,
                    password=password
                )
                print("✓ OpenReview client initialized")
            except Exception as e:
                print(f"Warning: Failed to initialize OpenReview client: {e}")
                print("Continuing without authentication (limited access)")
                self.client = openreview.api.OpenReviewClient(
                    baseurl='https://api2.openreview.net'
                )
    
    def fetch_papers(
        self,
        venue_id: str = "NeurIPS.cc/2024/Conference",
        limit: Optional[int] = None,
        *,
        accepted_only: bool = False,
        skip_paper_ids: Optional[Set[str]] = None,
        on_progress=None,
        content_fields: List[str] = None,
    ) -> List[Dict]:
        """
        获取会议的论文列表
        
        Args:
            venue_id: 会议 ID（例如 "NeurIPS.cc/2024/Conference"）
            limit: 限制返回的论文数量，None 表示获取全部
            accepted_only: 仅返回决策为 Accept 的论文（含 oral/spotlight/poster 等）
            skip_paper_ids: 跳过已存在的 paper_id（用于“追加抓取”模式）。当传入该参数时，limit 表示“返回的新论文数量上限”。
            content_fields: 需要获取的内容字段列表
        
        Returns:
            论文字典列表，每个字典包含论文的元数据
        """
        print(f"Fetching papers from {venue_id}...")
        self._init_client()
        
        if content_fields is None:
            content_fields = ['title', 'abstract', 'authors', 'keywords', 'pdf']
        
        papers = []
        
        try:
            # 构建 invitation（投稿邀请）
            submission_invitation = f"{venue_id}/-/Submission"

            print(f"Searching submissions with invitation: {submission_invitation}")

            # 关键优化：
            # - 旧实现使用 get_all_notes 会把该会议所有 submission（数千篇）一次性拉回来，即使 limit=100 也要等全量返回
            # - 改为 get_notes(limit/offset) 分页拉取，只拿到用户需要的条数
            page_size = int(os.getenv("MUJICA_OPENREVIEW_PAGE_SIZE", "200") or 200)
            page_size = max(20, min(page_size, 1000))

            offset = 0
            total_target = int(limit) if isinstance(limit, int) and limit > 0 else None
            fetched = 0  # 实际加入 papers 的数量（accepted_only 时为“accepted 数量”）
            seen = 0  # 扫描过的 submission 数量

            while True:
                batch_limit = page_size
                # 当启用 accepted_only 或 skip_paper_ids 时，需要“扫描更多 submission 才能凑够目标数量”，不做缩小优化
                if (total_target is not None) and (not accepted_only) and (not skip_paper_ids):
                    remain = total_target - fetched
                    if remain <= 0:
                        break
                    batch_limit = min(batch_limit, remain)

                submissions = self.client.get_notes(
                    invitation=submission_invitation,
                    details="replies",
                    limit=batch_limit,
                    offset=offset,
                )

                if not submissions:
                    break

                for submission in submissions:
                    seen += 1
                    paper_data = self._extract_paper_info(submission, content_fields, venue_id=venue_id)

                    if accepted_only:
                        decision = paper_data.get("decision")
                        d = str(decision or "").lower()
                        if "accept" not in d:
                            continue

                    if skip_paper_ids:
                        pid = str(paper_data.get("id") or "").strip()
                        if pid and pid in skip_paper_ids:
                            continue

                    papers.append(paper_data)
                    fetched += 1

                    if total_target is not None and fetched >= total_target:
                        break

                offset += len(submissions)

                # UI 进度回调（按“已满足目标数量”汇报；accepted_only/skip_existing 时扫描更多 submission）
                if callable(on_progress) and total_target is not None and total_target > 0:
                    try:
                        on_progress(
                            {
                                "stage": "fetch_papers",
                                "current": min(fetched, total_target),
                                "total": total_target,
                                "scanned": seen,
                                "accepted_only": bool(accepted_only),
                                "skip_existing": bool(skip_paper_ids),
                                "venue_id": venue_id,
                            }
                        )
                    except Exception:
                        pass

                # 进度日志
                if accepted_only:
                    if (seen % 50 == 0) or (total_target is not None and fetched >= total_target):
                        suffix = f"/{total_target}" if total_target is not None else ""
                        print(f"  Scanned {seen} submissions · accepted {fetched}{suffix}")
                else:
                    if fetched % 10 == 0:
                        suffix = f"/{total_target}" if total_target is not None else ""
                        print(f"  Processed {fetched}{suffix} papers")

                if total_target is not None and fetched >= total_target:
                    break

                if len(submissions) < batch_limit:
                    # 读到末尾
                    break

            if accepted_only:
                print(f"✓ Successfully fetched {len(papers)} accepted papers (scanned {seen} submissions)")
            else:
                print(f"✓ Successfully fetched {len(papers)} papers")

        except Exception as e:
            print(f"Error fetching papers: {e}")
            import traceback
            traceback.print_exc()
        
        return papers
    
    def _parse_numeric_score(self, value) -> Optional[float]:
        """
        OpenReview 的 rating/confidence 常见格式：
        - "8: Accept"
        - "3: High"
        - 8 / 8.0
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            m = re.search(r"(-?\d+(?:\.\d+)?)", value)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    return None
        return None

    def _extract_year_from_venue(self, venue_id: str) -> Optional[int]:
        m = re.search(r"\b(20\d{2})\b", venue_id or "")
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _extract_paper_info(self, submission, content_fields: List[str], venue_id: str) -> Dict:
        """
        从 OpenReview submission 对象中提取论文信息
        
        Args:
            submission: OpenReview Note 对象
            content_fields: 需要提取的字段列表
        
        Returns:
            包含论文信息的字典
        """
        paper = {
            "id": submission.id,
            "forum": submission.forum,
            "number": submission.number if hasattr(submission, 'number') else None,
            "venue_id": venue_id,
            "year": self._extract_year_from_venue(venue_id),
        }
        
        # 提取内容字段
        content = submission.content
        
        if 'title' in content_fields:
            paper['title'] = content.get('title', {}).get('value', 'Untitled')
        
        if 'abstract' in content_fields:
            paper['abstract'] = content.get('abstract', {}).get('value', '')
        
        if 'authors' in content_fields:
            authors = content.get('authors', {}).get('value', [])
            paper['authors'] = authors if isinstance(authors, list) else []
        
        if 'keywords' in content_fields:
            keywords = content.get('keywords', {}).get('value', [])
            paper['keywords'] = keywords if isinstance(keywords, list) else []
        
        if 'pdf' in content_fields:
            pdf_url = content.get('pdf', {}).get('value', '')
            # OpenReview 有时返回相对路径，如 "/pdf?id=..."
            if isinstance(pdf_url, str) and pdf_url.startswith("/"):
                pdf_url = "https://openreview.net" + pdf_url
            paper['pdf_url'] = pdf_url
        
        # 提取 TL;DR（如果有）
        paper['tldr'] = content.get('TL;DR', {}).get('value', '')
        
        def _val(obj: Dict, key: str, default=None):
            if not isinstance(obj, dict):
                return default
            v = obj.get(key, default)
            if isinstance(v, dict) and "value" in v:
                return v.get("value", default)
            return v

        def _parse_presentation(decision: Optional[str]) -> Optional[str]:
            """
            从 decision 字符串中提取展示类型（oral/spotlight/poster）。
            不同会议/年份的 decision 文本格式可能不同，因此做宽松匹配。
            """
            if not decision:
                return None
            d = str(decision).lower()
            # 常见形式：Accept (Oral) / Accept (Spotlight) / Accept (Poster)
            if "oral" in d:
                return "oral"
            if "spotlight" in d:
                return "spotlight"
            if "poster" in d:
                return "poster"
            # 有的会写 talk / presentation
            if "talk" in d:
                return "oral"
            # 接收但未标明展示类型
            if "accept" in d:
                return "unknown"
            return None

        # 提取决策信息（如果有评审）
        paper['decision'] = None
        paper['decision_text'] = None  # 决策 note 的正文（如 comment/理由等）
        paper['presentation'] = None
        paper['reviews'] = []
        paper['rebuttal_text'] = None  # 作者 rebuttal/response 的正文（可能有多条，合并保存）
        
        if hasattr(submission, 'details') and submission.details:
            replies = submission.details.get('replies', [])
            # 记录“最新的决策 note”（按时间选择）
            best_decision_cdate = -1
            best_decision_text_cdate = -1
            rebuttal_blocks: List[str] = []
            for reply in replies:
                # OpenReview v2: replies 通常是 dict，invitation 字段在 invitations(list) 中
                invs = reply.get("invitations") or []
                if isinstance(invs, str):
                    invs = [invs]
                if not isinstance(invs, list):
                    invs = []

                reply_content = reply.get('content', {}) or {}

                invs_l = [str(s).lower() for s in invs]
                is_official_review = any(("official_review" in s) or ("official review" in s) for s in invs_l)
                # decision invitation 常见包含 "Decision"；也可能只有 content 里带 decision 字段
                is_decision = any("decision" in s for s in invs_l)
                # meta review invitation：常见为 Meta_Review / Meta Review / metareview
                is_meta_review = any(
                    ("meta_review" in s) or ("metareview" in s) or ("meta review" in s) for s in invs_l
                )
                # rebuttal / author response invitation
                is_rebuttal = any(
                    ("rebuttal" in s)
                    or ("author_rebuttal" in s)
                    or ("author rebuttal" in s)
                    or ("author_response" in s)
                    or ("author response" in s)
                    or ("response" in s and "author" in s)
                    for s in invs_l
                )
                has_rating = any(k in reply_content for k in ["rating", "recommendation", "overall_rating", "score"])
                has_decision = "decision" in reply_content
                
                # 检查是否是评审
                # 注意：有些会议的作者回应会挂在 Official_Review 线程下（invitation 里包含 Official_Review + Rebuttal）
                # 这里必须优先把 rebuttal/meta_review/decision 识别出来，避免把“作者回应”误塞进 reviews。
                if (is_official_review or has_rating) and (not is_rebuttal) and (not is_decision) and (not has_decision) and (not is_meta_review):
                    review_content = reply_content

                    # 某些 review note 可能包含作者 rebuttal 字段（把它抽出来，避免和 reviewer 文本混在一起）
                    embedded_rebuttal = None
                    for kk in ["rebuttal", "author_response", "author comment", "author_comment", "response"]:
                        vv = _val(review_content, kk, None)
                        if isinstance(vv, str) and vv.strip():
                            embedded_rebuttal = vv.strip()
                            break
                    if embedded_rebuttal:
                        try:
                            cdate = int(reply.get("cdate") or reply.get("tcdate") or 0)
                        except Exception:
                            cdate = 0
                        tag = f"Author response (from review note, cdate={cdate})" if cdate else "Author response (from review note)"
                        rebuttal_blocks.append(f"{tag}:\n{embedded_rebuttal}".strip())

                    rating_raw = None
                    for k in ["rating", "recommendation", "overall_rating", "score"]:
                        if k in review_content:
                            rating_raw = _val(review_content, k, None)
                            break
                    confidence_raw = None
                    for k in ["confidence", "overall_confidence"]:
                        if k in review_content:
                            confidence_raw = _val(review_content, k, None)
                            break

                    # 尽量抽取“评审意见正文”（不同会议表单字段不同，做宽松兼容）
                    summary = _val(review_content, "summary", "") or ""
                    strengths = _val(review_content, "strengths", "") or ""
                    weaknesses = _val(review_content, "weaknesses", "") or ""

                    # 额外字段：把较长的文本字段也纳入（避免只有 checklist/短答）
                    skip_keys = {
                        # 打分/决策类
                        "rating",
                        "recommendation",
                        "overall_rating",
                        "score",
                        "confidence",
                        "overall_confidence",
                        "decision",
                        # 作者回应类（放到 paper-level rebuttal_text；不混进 reviewer 文本）
                        "rebuttal",
                        "author_response",
                        "author comment",
                        "author_comment",
                        "response",
                        # 常见短字段
                        "title",
                    }
                    extra_pairs = []
                    try:
                        for k in (review_content or {}).keys():
                            if k in skip_keys or k in {"summary", "strengths", "weaknesses"}:
                                continue
                            vv = _val(review_content, k, None)
                            if not isinstance(vv, str):
                                continue
                            ss = vv.strip()
                            if not ss:
                                continue
                            # 过滤掉过短的 Yes/No/checklist 类内容
                            if len(ss) < 20:
                                continue
                            extra_pairs.append((str(k), ss))
                    except Exception:
                        extra_pairs = []

                    # 只取前若干个，避免把整张表单都塞进单条 review（过长会影响吞吐/embedding 成本）
                    extra_pairs = extra_pairs[:10]

                    text_parts = []
                    if rating_raw is not None:
                        text_parts.append(f"Rating: {rating_raw}")
                    if confidence_raw is not None:
                        text_parts.append(f"Confidence: {confidence_raw}")
                    if summary.strip():
                        text_parts.append(f"Summary:\n{summary.strip()}")
                    if strengths.strip():
                        text_parts.append(f"Strengths:\n{strengths.strip()}")
                    if weaknesses.strip():
                        text_parts.append(f"Weaknesses:\n{weaknesses.strip()}")
                    for k, ss in extra_pairs:
                        text_parts.append(f"{k}:\n{ss}")
                    # FORCE STRING CONVERSION: Defensive coding against non-string items
                    review_text = "\n\n".join([str(x) for x in text_parts if x]).strip()

                    review_data = {
                        'rating_raw': str(rating_raw) if rating_raw is not None else 'N/A',
                        'rating': self._parse_numeric_score(rating_raw),
                        'confidence_raw': str(confidence_raw) if confidence_raw is not None else 'N/A',
                        'confidence': self._parse_numeric_score(confidence_raw),
                        'summary': summary,
                        'strengths': strengths,
                        'weaknesses': weaknesses,
                        'text': review_text,
                    }
                    paper['reviews'].append(review_data)

                # 检查是否是 rebuttal / author response
                elif is_rebuttal:
                    # 尽量保留作者回应的完整表单内容（Common concerns / Final comments 等可能在不同字段里）
                    skip_keys = {
                        "rating",
                        "recommendation",
                        "overall_rating",
                        "score",
                        "confidence",
                        "overall_confidence",
                        "decision",
                        "title",
                    }
                    blocks = []
                    seen_txt = set()
                    try:
                        for k in (reply_content or {}).keys():
                            if k in skip_keys:
                                continue
                            vv = _val(reply_content, k, None)
                            if not isinstance(vv, str):
                                continue
                            ss = vv.strip()
                            if not ss:
                                continue
                            if len(ss) < 3:
                                continue
                            if ss in seen_txt:
                                continue
                            seen_txt.add(ss)

                            label = str(k).replace("_", " ").strip()
                            # 常见主字段不额外加 label（直接作为段落），其他字段加 label 方便区分
                            if label.lower() in {"comment", "text", "reply", "response", "rebuttal", "description"}:
                                blocks.append(ss)
                            else:
                                blocks.append(f"{label}:\n{ss}")
                    except Exception:
                        blocks = []

                    main_text = "\n\n".join([x for x in blocks if x]).strip()
                    if main_text:
                        try:
                            cdate = int(reply.get("cdate") or reply.get("tcdate") or 0)
                        except Exception:
                            cdate = 0
                        tag = f"Rebuttal/Response (cdate={cdate})" if cdate else "Rebuttal/Response"
                        rebuttal_blocks.append(f"{tag}:\n{main_text}".strip())
                
                # 检查是否是决策
                elif is_decision or has_decision or is_meta_review:
                    decision_content = reply_content
                    decision_value = _val(decision_content, 'decision', None)
                    if decision_value is None:
                        decision_value = _val(decision_content, 'recommendation', None)

                    # 决策说明/理由通常在 comment / metareview / rationale 等字段里
                    comment = ""
                    for kk in ["comment", "metareview", "rationale", "decision_reason", "summary"]:
                        vv = _val(decision_content, kk, None)
                        if isinstance(vv, str) and vv.strip():
                            comment = vv.strip()
                            break

                    decision_text_parts = []
                    if decision_value is not None and str(decision_value).strip():
                        decision_text_parts.append(f"Decision: {str(decision_value).strip()}")
                    if comment:
                        decision_text_parts.append(comment)
                    decision_text = "\n\n".join([x for x in decision_text_parts if x]).strip() or None

                    try:
                        cdate = int(reply.get("cdate") or reply.get("tcdate") or 0)
                    except Exception:
                        cdate = 0

                    # 选择“最新的一条 decision note”作为最终 decision
                    if decision_value is not None and (cdate >= best_decision_cdate):
                        best_decision_cdate = cdate
                        paper['decision'] = decision_value
                        paper['presentation'] = _parse_presentation(paper.get("decision"))

                    # decision/meta_review 的正文：即使没有 decision_value，也要尽量保留（否则 UI 会觉得“没抓到”）
                    if decision_text is not None and (cdate >= best_decision_text_cdate):
                        best_decision_text_cdate = cdate
                        paper['decision_text'] = decision_text

            if rebuttal_blocks:
                paper["rebuttal_text"] = "\n\n---\n\n".join(rebuttal_blocks).strip()

            # 若 decision_text 没包含决策标签，但 papers.decision 有值，则前置一下，方便用户阅读
            try:
                dv = paper.get("decision")
                dt = paper.get("decision_text")
                if dv is not None and isinstance(dt, str) and dt.strip():
                    if "decision:" not in dt.lower():
                        paper["decision_text"] = f"Decision: {str(dv).strip()}\n\n{dt.strip()}".strip()
            except Exception:
                pass

        # 兜底：部分会议把“接收与展示类型”直接写在 submission.content['venue']（例如 "NeurIPS 2024 poster"）
        if paper.get("decision") is None:
            venue_value = content.get("venue", {}).get("value", "")
            if isinstance(venue_value, str) and venue_value.strip():
                vv = venue_value.strip()
                vv_lower = vv.lower()
                if "submitted to" not in vv_lower:
                    # 非 submitted 形式，通常已经有最终 venue（可视作已接收/已发布）
                    pres = _parse_presentation(vv)
                    if pres in {"oral", "spotlight", "poster"}:
                        paper["decision"] = f"Accept ({pres})"
                        paper["presentation"] = pres
                    elif "accept" in vv_lower:
                        paper["decision"] = vv
                        paper["presentation"] = _parse_presentation(vv)

        # 计算论文级别评分（兼容旧字段名 rating）
        numeric_ratings = [r.get("rating") for r in paper["reviews"] if isinstance(r.get("rating"), (int, float))]
        paper["rating"] = float(sum(numeric_ratings) / len(numeric_ratings)) if numeric_ratings else None
        
        return paper
    
    def fetch_paper_by_title(self, title: str) -> Optional[Dict]:
        """
        根据标题搜索特定论文
        
        Args:
            title: 论文标题
        
        Returns:
            论文字典，如果未找到则返回 None
        """
        print(f"Searching for paper: {title}")
        self._init_client()
        
        try:
            # 使用 search_notes 搜索
            notes = self.client.search_notes(term=title, limit=5)
            
            if not notes:
                print(f"  No paper found with title: {title}")
                return None
            
            # 找到最匹配的论文
            title_lower = title.lower().strip()
            for note in notes:
                note_title = note.content.get('title', {}).get('value', '').lower()
                if title_lower in note_title or note_title in title_lower:
                    print(f"  ✓ Found matching paper")
                    return self._extract_paper_info(note, ['title', 'abstract', 'authors', 'pdf'], venue_id="Unknown")
            
            # 如果没有完全匹配，返回第一个结果
            print(f"  Using best match (partial)")
            return self._extract_paper_info(notes[0], ['title', 'abstract', 'authors', 'pdf'], venue_id="Unknown")
            
        except Exception as e:
            print(f"Error searching for paper: {e}")
            return None
    
    def download_pdfs(self, papers: List[Dict], max_downloads: Optional[int] = None, on_progress=None):
        """
        下载论文 PDF
        
        Args:
            papers: 论文列表（需包含 pdf_url 字段）
            max_downloads: 最大下载数量限制
        """
        print(f"Downloading PDFs for {len(papers)} papers...")

        # 并发下载：显著加速（默认 6 线程），并将旧实现的 0.5s 固定 sleep 改为可配置
        max_workers = int(os.getenv("MUJICA_PDF_DOWNLOAD_WORKERS", "6") or 6)
        max_workers = max(1, min(max_workers, 16))
        delay = float(os.getenv("MUJICA_PDF_DOWNLOAD_DELAY", "0.0") or 0.0)
        delay = max(0.0, min(delay, 5.0))
        timeout = float(os.getenv("MUJICA_PDF_DOWNLOAD_TIMEOUT", "60") or 60)
        retries = int(os.getenv("MUJICA_PDF_DOWNLOAD_RETRIES", "2") or 2)
        retries = max(0, min(retries, 5))

        force_redownload = (os.getenv("MUJICA_PDF_FORCE_REDOWNLOAD", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        validate_existing = (os.getenv("MUJICA_PDF_VALIDATE_EXISTING", "1") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        eof_check = (os.getenv("MUJICA_PDF_EOF_CHECK", "1") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        try:
            min_bytes = int(os.getenv("MUJICA_PDF_MIN_BYTES", "10240") or 10240)  # 10KB
        except Exception:
            min_bytes = 10240
        min_bytes = max(0, min(min_bytes, 50_000_000))

        # thread-local session（减少重复握手/提升吞吐）
        _local = threading.local()

        def _session():
            s = getattr(_local, "session", None)
            if s is None:
                s = requests.Session()
                _local.session = s
            return s

        def _is_valid_pdf(path: str) -> bool:
            if not path or not os.path.exists(path):
                return False
            try:
                sz = os.path.getsize(path)
                if min_bytes > 0 and sz < min_bytes:
                    return False
                with open(path, "rb") as f:
                    head = f.read(5)
                    if not head.startswith(b"%PDF-"):
                        return False
                    if eof_check:
                        # EOF 通常在尾部附近，读最后 2KB 检查
                        try:
                            tail_size = 2048
                            if sz > tail_size:
                                f.seek(-tail_size, os.SEEK_END)
                            tail = f.read(tail_size)
                        except Exception:
                            tail = b""
                        if b"%%EOF" not in tail:
                            return False
                return True
            except Exception:
                return False

        def _download_one(idx: int, paper: Dict) -> Dict:
            pdf_url = paper.get("pdf_url", "")
            if not pdf_url:
                return {"idx": idx, "paper_id": paper.get("id"), "status": "skipped", "error": "no_pdf_url"}

            paper_id = paper.get("id", f"paper_{idx}")
            filename = f"{paper_id}.pdf"
            filepath = os.path.join(self.pdf_dir, filename)

            if (not force_redownload) and os.path.exists(filepath):
                if (not validate_existing) or _is_valid_pdf(filepath):
                    paper["pdf_path"] = filepath
                    return {"idx": idx, "paper_id": paper_id, "status": "exists", "filepath": filepath}
                # 存在但疑似损坏：触发重下
                return {"idx": idx, "paper_id": paper_id, "status": "need_redownload", "filepath": filepath}

            last_err = None
            for attempt in range(retries + 1):
                try:
                    if delay > 0:
                        # 加一点 jitter，避免多线程同时打爆
                        time.sleep(delay * (0.85 + random.random() * 0.30))
                    resp = _session().get(
                        pdf_url,
                        timeout=timeout,
                        stream=True,
                        headers={
                            "User-Agent": "MUJICA/1.0 (+https://openreview.net)",
                            "Accept": "application/pdf,*/*;q=0.8",
                        },
                    )
                    resp.raise_for_status()
                    with open(filepath, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)
                    # 基本校验（避免写入 HTML/错误页）
                    if validate_existing and (not _is_valid_pdf(filepath)):
                        raise RuntimeError("downloaded_file_is_not_valid_pdf")
                    paper["pdf_path"] = filepath
                    return {"idx": idx, "paper_id": paper_id, "status": "downloaded", "filepath": filepath}
                except Exception as e:
                    last_err = e
                    # 简单退避
                    if attempt < retries:
                        # 429/503 等更长退避；如果有 Retry-After，优先遵守
                        wait = min(1.0 * (2**attempt), 8.0)
                        try:
                            resp = getattr(e, "response", None)
                            if resp is not None and hasattr(resp, "status_code"):
                                sc = int(getattr(resp, "status_code") or 0)
                                if sc in {429, 503, 502, 504}:
                                    ra = None
                                    try:
                                        ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                                    except Exception:
                                        ra = None
                                    if ra is not None:
                                        try:
                                            wait = max(wait, float(ra))
                                        except Exception:
                                            pass
                                    wait = max(wait, 2.0)
                                if sc == 404:
                                    # 404 基本不可能成功，直接退出重试
                                    break
                        except Exception:
                            pass
                        time.sleep(min(wait, 60.0))
            return {"idx": idx, "paper_id": paper_id, "status": "failed", "error": str(last_err)}

        # 预扫描：把“已存在且有效”的直接标记为 exists，不占用下载任务
        pre_results: List[Dict] = []
        download_targets: List[tuple[int, Dict]] = []
        exists = 0
        skipped = 0
        need_redownload = 0

        for idx, p in enumerate(papers):
            pdf_url = p.get("pdf_url", "")
            if not pdf_url:
                skipped += 1
                pre_results.append({"idx": idx, "paper_id": p.get("id"), "status": "skipped", "error": "no_pdf_url"})
                continue

            paper_id = p.get("id", f"paper_{idx}")
            filepath = os.path.join(self.pdf_dir, f"{paper_id}.pdf")

            if (not force_redownload) and os.path.exists(filepath):
                if (not validate_existing) or _is_valid_pdf(filepath):
                    p["pdf_path"] = filepath
                    exists += 1
                    pre_results.append({"idx": idx, "paper_id": paper_id, "status": "exists", "filepath": filepath})
                    continue
                # 存在但疑似损坏：加入下载队列
                need_redownload += 1

            download_targets.append((idx, p))

        # max_downloads：限制“需要网络下载”的数量（不包含 exists）
        if isinstance(max_downloads, int) and max_downloads > 0:
            download_targets = download_targets[:max_downloads]

        total = len(pre_results) + len(download_targets)
        done = 0
        downloaded = 0
        failed = 0
        redownloaded = 0

        # 先把预扫描结果也计入进度（exists/skipped）
        for r in pre_results:
            done += 1
            if callable(on_progress):
                try:
                    on_progress(
                        {
                            "stage": "download_pdf",
                            "current": done,
                            "total": total,
                            "paper_id": r.get("paper_id"),
                            "status": r.get("status"),
                        }
                    )
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_download_one, idx, p) for idx, p in download_targets]
            for fut in as_completed(futures):
                r = fut.result()
                done += 1
                status = r.get("status")
                if status == "downloaded":
                    downloaded += 1
                elif status == "need_redownload":
                    redownloaded += 1
                elif status == "failed":
                    failed += 1

                if callable(on_progress):
                    try:
                        on_progress(
                            {
                                "stage": "download_pdf",
                                "current": done,
                                "total": total,
                                "paper_id": r.get("paper_id"),
                                "status": status,
                            }
                        )
                    except Exception:
                        pass

        succeeded = exists + downloaded
        print(
            f"\n✓ Download complete: {succeeded} ok (downloaded={downloaded}, exists={exists}), "
            f"{failed} failed, {skipped} skipped"
            f" (workers={max_workers}, delay={delay}s, retries={retries}, timeout={timeout}s, "
            f"force_redownload={force_redownload}, validate_existing={validate_existing}, min_bytes={min_bytes})"
        )
    
    def get_venue_stats(self, venue_id: str = "NeurIPS.cc/2024/Conference") -> Dict:
        """
        获取会议的统计信息
        
        Args:
            venue_id: 会议 ID
        
        Returns:
            包含统计信息的字典
        """
        print(f"Fetching stats for {venue_id}...")
        self._init_client()
        
        stats = {
            "venue_id": venue_id,
            "total_submissions": 0,
            "accepted": 0,
            "rejected": 0,
            "pending": 0
        }
        
        try:
            submission_invitation = f"{venue_id}/-/Submission"
            submissions = self.client.get_all_notes(
                invitation=submission_invitation,
                details='replies'
            )
            
            stats["total_submissions"] = len(submissions)
            
            # 统计决策
            for submission in submissions:
                if hasattr(submission, 'details') and submission.details:
                    replies = submission.details.get('replies', [])
                    for reply in replies:
                        invs = reply.get("invitations") or []
                        if isinstance(invs, str):
                            invs = [invs]
                        if any("Decision" in str(s) for s in (invs or [])) or ("decision" in (reply.get("content") or {})):
                            decision = (reply.get('content', {}) or {}).get('decision', {})
                            if isinstance(decision, dict):
                                decision = decision.get('value', '')
                            decision = str(decision or '').lower()
                            if 'accept' in decision:
                                stats["accepted"] += 1
                            elif 'reject' in decision:
                                stats["rejected"] += 1
                            break
                    else:
                        stats["pending"] += 1
            
            print(f"✓ Stats: {stats['total_submissions']} total, "
                  f"{stats['accepted']} accepted, "
                  f"{stats['rejected']} rejected, "
                  f"{stats['pending']} pending")
            
        except Exception as e:
            print(f"Error fetching stats: {e}")
        
        return stats
