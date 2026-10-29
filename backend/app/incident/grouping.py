"""
Error grouping in two steps.

1. EXACT: records with the same service, exception type and masked message are one group.
   Numbers, ids and addresses are hidden by the masking, so "waiting=14" and "waiting=22" do not split a group.

2. SIMILAR: the message patterns that remain are compared with TF-IDF and cosine similarity. Patterns whose
   wording is close enough (the threshold is configurable) are merged into one group.
   This finds RELATED messages. It does not prove they share a root cause, and the explanation says so.

Only WARNING-or-worse records (and HTTP 5xx) are grouped; routine INFO traffic is left alone.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.incident.types import DetectionParams, Group, Rec
from app.ingestion.normalize import LEVELS

_PLACEHOLDER = re.compile(r"<[A-Z]+>")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{1,}")


def _similarity_text(template: str) -> str:
    """Words only: placeholders such as <NUM> carry no meaning and would make unrelated lines look alike."""
    return " ".join(_TOKEN.findall(_PLACEHOLDER.sub(" ", template))).lower()


def _title(service: str, exception_type: str | None, template: str) -> str:
    body = template if not exception_type or exception_type in template else f"{exception_type}: {template}"
    body = body if len(body) <= 110 else body[:107] + "..."
    return f"{service}: {body}"


def _max_level(records: list[Rec]) -> str:
    return LEVELS[max(r.rank for r in records)]


def build_groups(records: list[Rec], params: DetectionParams) -> list[Group]:
    """Group the problem records. Returns groups sorted by size, largest first."""
    # ---- step 1: exact ------------------------------------------------------------------------
    buckets: dict[tuple[str, str, str], list[Rec]] = defaultdict(list)
    for record in records:
        if record.is_problem:
            buckets[(record.service, record.exception_type or "", record.template)].append(record)
    if not buckets:
        return []

    # ---- step 2: similar wording --------------------------------------------------------------
    keys = list(buckets)
    cluster_of, similarity = _cluster_templates(keys, params)

    members: dict[int, list[int]] = defaultdict(list)  # cluster number -> positions in `keys`
    for position, cluster in enumerate(cluster_of):
        members[cluster].append(position)

    groups: list[Group] = []
    for index, positions in enumerate(members.values()):
        cluster_keys = [keys[p] for p in positions]
        group_records = sorted((r for k in cluster_keys for r in buckets[k]), key=lambda r: (r.ts is None, r.ts, r.id))
        cluster_keys.sort(key=lambda k: -len(buckets[k]))
        main_service, main_exception, main_template = cluster_keys[0]
        services = sorted({k[0] for k in cluster_keys})
        exceptions = sorted({k[1] for k in cluster_keys if k[1]})
        times = [r.ts for r in group_records if r.ts is not None]
        member_info = [
            {"service": k[0], "exception_type": k[1] or None, "template": k[2], "count": len(buckets[k])}
            for k in cluster_keys
        ]
        if len(cluster_keys) == 1:
            method = "exact"
            explanation = (
                f"Grouped because {len(group_records)} record(s) have the same service ({main_service}), "
                f"{'the same exception type, ' if main_exception else ''}and the same message once numbers, ids and "
                "addresses are masked."
            )
        else:
            method = "similarity"
            sub = similarity[np.ix_(positions, positions)]
            low = float(sub[np.triu_indices_from(sub, k=1)].min())
            explanation = (
                f"{len(cluster_keys)} message patterns were merged because their wording is similar "
                f"(TF-IDF cosine similarity at least {params.similarity_threshold:.2f}; the least similar pair scores {low:.2f}). "
                "Similar wording means the messages are related. It does not prove they have the same root cause."
            )
        groups.append(Group(
            key=f"g{index}", title=_title(main_service, main_exception, main_template), template=main_template,
            services=services, exception_types=exceptions, method=method, explanation=explanation,
            member_templates=member_info, records=group_records,
            first_seen=min(times) if times else None, last_seen=max(times) if times else None,
            max_level=_max_level(group_records),
        ))
    groups.sort(key=lambda g: (-g.count, g.title))
    for number, group in enumerate(groups):
        group.key = f"g{number}"
    return groups


def _cluster_templates(keys: list[tuple[str, str, str]], params: DetectionParams) -> tuple[list[int], np.ndarray]:
    """Return a cluster number for every (service, exception, template) key, and the similarity matrix used."""
    size = len(keys)
    alone = (list(range(size)), np.eye(size))
    if size < 2:
        return alone
    texts = [_similarity_text(k[2]) for k in keys]
    if not any(texts):
        return alone
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit_transform(texts)
    except ValueError:  # every text was empty after cleaning
        return alone
    similarity = cosine_similarity(matrix)
    distance = np.clip(1.0 - similarity, 0.0, 1.0)
    # Messages from different services are only compared when the user allows it.
    if not params.merge_across_services:
        services = np.array([k[0] for k in keys])
        different = services[:, None] != services[None, :]
        distance[different] = 1.0
        similarity = np.where(different, 0.0, similarity)
    np.fill_diagonal(distance, 0.0)
    model = AgglomerativeClustering(
        n_clusters=None, metric="precomputed", linkage="average", distance_threshold=1.0 - params.similarity_threshold)
    return [int(c) for c in model.fit_predict(distance)], similarity


def top_counter(values: list[str], limit: int = 5) -> list[tuple[str, int]]:
    return Counter(values).most_common(limit)
