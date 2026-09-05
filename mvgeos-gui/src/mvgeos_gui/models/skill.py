"""Skill info model for inspector panels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SkillInfo:
    """Summary of a discovered Skill rendered in the context inspector."""

    name: str
    description: str = ""
    scope: str = ""
    path: str = ""
    invoked: bool = False
