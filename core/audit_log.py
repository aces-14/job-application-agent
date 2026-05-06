import json
import os
from datetime import datetime
from typing import Any, Dict, List
from dataclasses import dataclass, field, asdict
from core.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class AuditEntry:
    timestamp: str
    step: str
    action: str
    input_summary: str
    output_summary: str
    reasoning: str
    confidence: str
    warnings: List[str] = field(default_factory=list)

@dataclass
class AuditLog:
    session_id: str
    started_at: str
    candidate_name: str
    job_title: str
    company: str
    entries: List[AuditEntry] = field(default_factory=list)
    integrity_passed: bool = True
    final_match_score: float = 0.0

    def add_entry(
        self,
        step: str,
        action: str,
        input_summary: str,
        output_summary: str,
        reasoning: str,
        confidence: str = "high",
        warnings: List[str] = None
    ):
        entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            step=step,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            reasoning=reasoning,
            confidence=confidence,
            warnings=warnings or []
        )
        self.entries.append(entry)
        logger.info(f"Audit [{step}]: {action}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, output_dir: str = "outputs") -> str:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{output_dir}/audit_{self.session_id}.json"
        with open(filename, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Audit log saved: {filename}")
        return filename

def create_audit_log(
    candidate_name: str,
    job_title: str,
    company: str
) -> AuditLog:
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return AuditLog(
        session_id=session_id,
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        candidate_name=candidate_name,
        job_title=job_title,
        company=company
    )