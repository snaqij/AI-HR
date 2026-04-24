"""Competency mapper.

Converts role config competency models into executable evaluation logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CompetencyWeight:
    """Competency weight."""
    
    competency_id: str
    description: str
    weight: float
    evidence_types: List[str]
    is_universal: bool


@dataclass
class CompetencyModel:
    """Competency model."""
    
    role_id: str
    universal_competencies: List[CompetencyWeight]
    role_competencies: List[CompetencyWeight]
    total_weight: float
    
    def get_all_competencies(self) -> List[CompetencyWeight]:
        """Get all competencies."""
        return self.universal_competencies + self.role_competencies
    
    def get_competency_by_id(self, competency_id: str) -> Optional[CompetencyWeight]:
        """Get a competency by ID."""
        for comp in self.get_all_competencies():
            if comp.competency_id == competency_id:
                return comp
        return None
    
    def get_evidence_types(self) -> List[str]:
        """Get all evidence types."""
        evidence_types = set()
        for comp in self.get_all_competencies():
            evidence_types.update(comp.evidence_types)
        return sorted(evidence_types)


class CompetencyMapper:
    """Competency mapper."""
    
    def __init__(self):
        logger.info("competency.mapper.initialized")
    
    def build_competency_model(self, role_config: Dict) -> CompetencyModel:
        """
        Build a competency model from a role config.
        
        Args:
            role_config: Role config dict
        
        Returns:
            CompetencyModel instance
        """
        if not role_config:
            raise ValueError("role_config cannot be None or empty")
        
        role_id = role_config.get("role", {}).get("id", "_base")
        
        # Parse universal competencies
        universal_competencies = self._parse_competencies(
            role_config.get("universal_competencies", {}),
            is_universal=True
        )
        
        # Parse role-specific competencies
        role_competencies = self._parse_competencies(
            role_config.get("role_competencies", {}),
            is_universal=False
        )
        
        # Calculate total weight
        total_weight = sum(c.weight for c in universal_competencies + role_competencies)
        
        model = CompetencyModel(
            role_id=role_id,
            universal_competencies=universal_competencies,
            role_competencies=role_competencies,
            total_weight=total_weight
        )
        
        logger.info(
            "competency.model.built",
            extra={
                "role_id": role_id,
                "universal_count": len(universal_competencies),
                "role_count": len(role_competencies),
                "total_weight": total_weight
            }
        )
        
        return model
    
    def _parse_competencies(
        self,
        competencies_config: Dict,
        is_universal: bool
    ) -> List[CompetencyWeight]:
        """
        Parse a competencies config block.
        
        Args:
            competencies_config: Competencies config dict
            is_universal: Whether these are universal competencies
        
        Returns:
            List of CompetencyWeight
        """
        competencies = []
        
        for comp_id, comp_config in competencies_config.items():
            if not isinstance(comp_config, dict):
                continue
            
            weight = float(comp_config.get("weight", 0.0))
            description = str(comp_config.get("description", comp_id))
            evidence_types = comp_config.get("evidence_types", [])
            
            if not isinstance(evidence_types, list):
                evidence_types = []
            
            evidence_types = [str(et).strip() for et in evidence_types if str(et).strip()]
            
            competency = CompetencyWeight(
                competency_id=comp_id,
                description=description,
                weight=weight,
                evidence_types=evidence_types,
                is_universal=is_universal
            )
            
            competencies.append(competency)
        
        return competencies
    
    def calculate_competency_weights(
        self,
        role_config: Dict,
        normalize: bool = True
    ) -> Dict[str, float]:
        """
        Calculate a competency weights dict.
        
        Args:
            role_config: Role config
            normalize: Whether to normalize weights so they sum to 1.0
        
        Returns:
            Dict of {competency_id: weight}
        """
        model = self.build_competency_model(role_config)
        
        weights = {}
        for comp in model.get_all_competencies():
            weights[comp.competency_id] = comp.weight
        
        if normalize and model.total_weight > 0:
            for comp_id in weights:
                weights[comp_id] = weights[comp_id] / model.total_weight
        
        return weights
    
    def get_evidence_requirements(self, role_config: Dict) -> Dict[str, List[str]]:
        """
        Get the evidence requirements mapping.
        
        Args:
            role_config: Role config
        
        Returns:
            Dict of {competency_id: [evidence_types]}
        """
        model = self.build_competency_model(role_config)
        
        evidence_map = {}
        for comp in model.get_all_competencies():
            evidence_map[comp.competency_id] = comp.evidence_types
        
        return evidence_map
    
    def validate_competency_config(self, role_config: Dict) -> tuple[bool, List[str]]:
        """
        Validate the competency configuration.
        
        Args:
            role_config: Role config
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        try:
            model = self.build_competency_model(role_config)
            
            # Check total weight
            if model.total_weight <= 0:
                errors.append("Total competency weight must be greater than 0")
            
            # Check weight ranges
            for comp in model.get_all_competencies():
                if comp.weight < 0:
                    errors.append(f"Competency '{comp.competency_id}' has negative weight: {comp.weight}")
                if comp.weight > 1.0:
                    errors.append(f"Competency '{comp.competency_id}' has weight > 1.0: {comp.weight}")
            
            # Check evidence types
            for comp in model.get_all_competencies():
                if not comp.evidence_types:
                    errors.append(f"Competency '{comp.competency_id}' has no evidence types")
            
        except Exception as e:
            errors.append(f"Failed to build competency model: {str(e)}")
        
        return len(errors) == 0, errors
