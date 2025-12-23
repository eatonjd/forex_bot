#!/usr/bin/env python3
"""
Ensemble Trading Module.

Combines predictions from multiple trained models to make more robust
trading decisions. Ensemble methods reduce overfitting and capture
different market patterns.

Ensemble Strategies:
- Majority Vote: Most common action wins
- Weighted Vote: Weight by model performance
- Conservative: Only trade when all models agree
- Confidence Weighted: Weight by prediction confidence
- Regime-Specific: Use different models for different regimes
"""

import os
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import numpy as np
from stable_baselines3 import PPO


class EnsembleStrategy(Enum):
    """Ensemble combination strategies."""

    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    CONSERVATIVE = "conservative"
    CONFIDENCE = "confidence"
    REGIME_SPECIFIC = "regime_specific"


@dataclass
class ModelConfig:
    """Configuration for a single model in the ensemble."""

    path: str
    name: str
    weight: float = 1.0
    regime: Optional[str] = None  # Which regime is this model best for
    description: str = ""
    feature_type: str = "standard"  # 'standard' (44 feats) or 'volume' (13 feats)


class EnsembleTrader:
    """
    Combines multiple trading models for better predictions.

    Each model can be trained on different:
    - Time periods (bull vs bear markets)
    - Hyperparameters (aggressive vs conservative)
    - Symbols (specialist models)
    - Algorithms (PPO, A2C, etc.)
    """

    def __init__(
        self,
        model_configs: List[ModelConfig],
        strategy: EnsembleStrategy = EnsembleStrategy.WEIGHTED_VOTE,
        agreement_threshold: float = 0.6,
    ):
        """
        Initialize the ensemble trader.

        Args:
            model_configs: List of model configurations
            strategy: Ensemble combination strategy
            agreement_threshold: Minimum agreement for weighted strategies
        """
        self.model_configs = model_configs
        self.strategy = strategy
        self.agreement_threshold = agreement_threshold
        self.models: List[PPO] = []
        self.action_names = ["HOLD", "BUY", "SELL"]

        # Load all models
        self._load_models()

    def _load_models(self):
        """Load all models in the ensemble."""
        print(f"📦 Loading {len(self.model_configs)} models for ensemble...")

        for config in self.model_configs:
            if os.path.exists(config.path):
                try:
                    model = PPO.load(config.path)
                    self.models.append(model)
                    print(f"   ✅ {config.name}: {config.description or 'Loaded'}")
                except Exception as e:
                    print(f"   ❌ {config.name}: Failed to load - {e}")
            else:
                print(f"   ⚠️  {config.name}: File not found")

        print(f"✅ Loaded {len(self.models)}/{len(self.model_configs)} models\n")

    def predict_all(
        self, observation: Union[np.ndarray, Dict[str, np.ndarray]]
    ) -> List[Tuple[int, np.ndarray]]:
        """
        Get predictions from all models.

        Args:
            observation: Single observation vector OR dict of vectors {"standard": ..., "volume": ...}
        """
        predictions = []

        for i, model in enumerate(self.models):
            try:
                # Select correct observation based on feature type
                feature_type = self.model_configs[i].feature_type

                if isinstance(observation, dict):
                    if feature_type in observation:
                        obs = observation[feature_type]
                    else:
                        obs = observation.get(
                            "standard", next(iter(observation.values()))
                        )
                else:
                    obs = observation

                # Get action and probabilities
                action, _ = model.predict(obs, deterministic=True)

                try:
                    # Get probabilities for weighted voting
                    obs_tensor = model.policy.obs_to_tensor(obs)[0]
                    action_dist = model.policy.get_distribution(obs_tensor)
                    # For Categorical distribution
                    action_probs = action_dist.distribution.probs.detach().numpy()[0]
                except:
                    # Fallback if probability extraction fails
                    action_probs = np.array([0.33, 0.33, 0.34])
                    # If it's deterministic 'action' implies 100% confidence
                    action_probs[int(action)] = 0.9
                    action_probs[(int(action) + 1) % 3] = 0.05
                    action_probs[(int(action) + 2) % 3] = 0.05

                predictions.append((int(action), action_probs))
            except Exception as e:
                print(f"Error predicting with model {self.model_configs[i].name}: {e}")
                predictions.append((0, np.array([1.0, 0.0, 0.0])))  # Default HOLD

        return predictions

    def ensemble_predict(
        self,
        observation: np.ndarray,
        regime: Optional[str] = None,
    ) -> Tuple[int, Dict]:
        """
        Get ensemble prediction combining all models.

        Args:
            observation: Environment observation
            regime: Current market regime (for regime-specific strategy)

        Returns:
            Tuple of (action, analysis_dict)
        """
        predictions = self.predict_all(observation)

        if self.strategy == EnsembleStrategy.MAJORITY_VOTE:
            return self._majority_vote(predictions)

        elif self.strategy == EnsembleStrategy.WEIGHTED_VOTE:
            return self._weighted_vote(predictions)

        elif self.strategy == EnsembleStrategy.CONSERVATIVE:
            return self._conservative(predictions)

        elif self.strategy == EnsembleStrategy.CONFIDENCE:
            return self._confidence_weighted(predictions)

        elif self.strategy == EnsembleStrategy.REGIME_SPECIFIC:
            return self._regime_specific(predictions, regime)

        else:
            return self._majority_vote(predictions)

    def _majority_vote(
        self, predictions: List[Tuple[int, np.ndarray]]
    ) -> Tuple[int, Dict]:
        """Simple majority vote - most popular action wins."""
        actions = [p[0] for p in predictions]

        vote_counts = {
            0: actions.count(0),  # HOLD
            1: actions.count(1),  # BUY
            2: actions.count(2),  # SELL
        }

        winning_action = max(vote_counts, key=vote_counts.get)
        agreement = vote_counts[winning_action] / len(actions)

        # Build per-model vote breakdown
        model_votes = {
            self.model_configs[i].name: self.action_names[actions[i]]
            for i in range(len(actions))
        }

        analysis = {
            "strategy": "majority_vote",
            "vote_counts": vote_counts,
            "agreement": agreement,
            "individual_predictions": [self.action_names[a] for a in actions],
            "model_names": [cfg.name for cfg in self.model_configs],
            "model_votes": model_votes,
        }

        return winning_action, analysis

    def _weighted_vote(
        self, predictions: List[Tuple[int, np.ndarray]]
    ) -> Tuple[int, Dict]:
        """Weight votes by model weights."""
        action_scores = {0: 0.0, 1: 0.0, 2: 0.0}
        actions = [p[0] for p in predictions]

        for i, (action, _) in enumerate(predictions):
            weight = (
                self.model_configs[i].weight if i < len(self.model_configs) else 1.0
            )
            action_scores[action] += weight

        # Normalize
        total_weight = sum(action_scores.values())
        for a in action_scores:
            action_scores[a] /= total_weight

        winning_action = max(action_scores, key=action_scores.get)

        # Build per-model vote breakdown
        model_votes = {
            self.model_configs[i].name: self.action_names[actions[i]]
            for i in range(len(actions))
        }

        analysis = {
            "strategy": "weighted_vote",
            "action_scores": action_scores,
            "weights_used": [c.weight for c in self.model_configs[: len(predictions)]],
            "model_names": [cfg.name for cfg in self.model_configs],
            "model_votes": model_votes,
        }

        return winning_action, analysis

    def _conservative(
        self, predictions: List[Tuple[int, np.ndarray]]
    ) -> Tuple[int, Dict]:
        """Only trade when all models agree. Otherwise HOLD."""
        actions = [p[0] for p in predictions]

        if len(set(actions)) == 1:  # All agree
            return actions[0], {
                "strategy": "conservative",
                "unanimous": True,
                "agreement_action": self.action_names[actions[0]],
            }

        # No consensus - default to HOLD
        vote_counts = {a: actions.count(a) for a in set(actions)}

        return 0, {  # HOLD
            "strategy": "conservative",
            "unanimous": False,
            "vote_counts": vote_counts,
            "message": "No consensus - defaulting to HOLD",
        }

    def _confidence_weighted(
        self, predictions: List[Tuple[int, np.ndarray]]
    ) -> Tuple[int, Dict]:
        """Weight by prediction confidence (probability of chosen action)."""
        action_scores = {0: 0.0, 1: 0.0, 2: 0.0}
        confidences = []

        for action, probs in predictions:
            confidence = probs[action]  # Probability of the chosen action
            confidences.append(float(confidence))
            action_scores[action] += confidence

        # Normalize
        total = sum(action_scores.values())
        if total > 0:
            for a in action_scores:
                action_scores[a] /= total

        winning_action = max(action_scores, key=action_scores.get)

        analysis = {
            "strategy": "confidence_weighted",
            "action_scores": action_scores,
            "individual_confidences": confidences,
            "avg_confidence": np.mean(confidences),
        }

        return winning_action, analysis

    def _regime_specific(
        self,
        predictions: List[Tuple[int, np.ndarray]],
        regime: Optional[str],
    ) -> Tuple[int, Dict]:
        """Use models best suited for the current regime."""
        if regime is None:
            # Fall back to weighted vote
            return self._weighted_vote(predictions)

        # Find models that match the regime
        regime_models = []
        other_models = []

        for i, config in enumerate(self.model_configs):
            if config.regime == regime or config.regime == "all":
                regime_models.append(
                    (i, predictions[i] if i < len(predictions) else None)
                )
            else:
                other_models.append(
                    (i, predictions[i] if i < len(predictions) else None)
                )

        # Weight regime-specific models more heavily
        action_scores = {0: 0.0, 1: 0.0, 2: 0.0}

        for i, pred in regime_models:
            if pred:
                action_scores[pred[0]] += 2.0  # Double weight for matching regime

        for i, pred in other_models:
            if pred:
                action_scores[pred[0]] += 0.5  # Half weight for non-matching

        # Normalize
        total = sum(action_scores.values())
        if total > 0:
            for a in action_scores:
                action_scores[a] /= total

        winning_action = max(action_scores, key=action_scores.get)

        # Build per-model vote breakdown
        actions = [p[0] if p else 0 for p in predictions]
        model_votes = {
            self.model_configs[i].name: self.action_names[actions[i]]
            for i in range(min(len(actions), len(self.model_configs)))
        }

        analysis = {
            "strategy": "regime_specific",
            "current_regime": regime,
            "regime_models_count": len(regime_models),
            "other_models_count": len(other_models),
            "action_scores": action_scores,
            "individual_predictions": [
                self.action_names[p[0]] if p else "N/A" for p in predictions
            ],
            "model_names": [cfg.name for cfg in self.model_configs],
            "model_votes": model_votes,
        }

        return winning_action, analysis

    def get_ensemble_summary(self) -> Dict:
        """Get summary of the ensemble configuration."""
        return {
            "num_models": len(self.models),
            "strategy": self.strategy.value,
            "models": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "regime": c.regime,
                    "description": c.description,
                }
                for c in self.model_configs
            ],
        }

    def print_prediction_analysis(
        self, observation: np.ndarray, regime: Optional[str] = None
    ):
        """Print detailed analysis of ensemble prediction."""
        action, analysis = self.ensemble_predict(observation, regime)

        print("\n" + "=" * 60)
        print("🎯 ENSEMBLE PREDICTION ANALYSIS")
        print("=" * 60)
        print(f"Strategy: {analysis.get('strategy', 'unknown').upper()}")
        print(f"Final Action: {self.action_names[action]}")

        if "vote_counts" in analysis:
            print(f"\nVote Breakdown:")
            for act, count in analysis["vote_counts"].items():
                bar = "█" * count
                print(f"   {self.action_names[act]}: {bar} ({count})")

        if "action_scores" in analysis:
            print(f"\nAction Scores:")
            for act, score in analysis["action_scores"].items():
                bar = "█" * int(score * 20)
                print(f"   {self.action_names[act]}: {bar} ({score:.2%})")

        if "individual_predictions" in analysis:
            print(f"\nIndividual Model Predictions:")
            for i, pred in enumerate(analysis["individual_predictions"]):
                name = (
                    self.model_configs[i].name
                    if i < len(self.model_configs)
                    else f"Model {i}"
                )
                print(f"   {name}: {pred}")

        if "unanimous" in analysis:
            print(f"\nUnanimous: {'Yes ✓' if analysis['unanimous'] else 'No ✗'}")

        if "agreement" in analysis:
            print(f"Agreement: {analysis['agreement']:.0%}")

        print("=" * 60)

        return action, analysis


def create_default_ensemble(symbol: str = "QQQ") -> EnsembleTrader:
    """
    Create a default ensemble with available models for the given symbol.
    Includes both basic and advanced (Sharpe, multi-symbol) models.

    Args:
        symbol: Symbol to load specific models for (e.g., "TQQQ")

    Returns:
        EnsembleTrader with configured models
    """
    # Define potential models - includes basic and advanced
    model_configs = []

    # 0. UNIVERSAL FLEET (Priority)
    # These are the new models trained by 'train_universal_fleet.py'
    universal_models = [
        (
            "Universal_Balanced_v2.zip",
            "Universal Balanced v2",
            2.0,
            "all",
            "Bear-market optimized (Universal)",
        ),
        (
            "Universal_Sharpe.zip",
            "Universal Sharpe",
            1.5,
            "all",
            "Balanced growth (Universal)",
        ),
        (
            "Universal_Sortino.zip",
            "Universal Sortino",
            1.2,
            "volatile",
            "Downside protection (Universal)",
        ),
        (
            "Universal_Calmar.zip",
            "Universal Calmar",
            1.2,
            "bear",
            "Drawdown minimizer (Universal)",
        ),
        (
            "Universal_Omega.zip",
            "Universal Omega",
            1.5,
            "bull",
            "Aggressive growth (Universal)",
        ),
        (
            "Universal_Volume_Expert.zip",
            "Universal Volume",
            1.6,
            "all",
            "Volume/Microstructure Specialist",
        ),
    ]

    universal_configs = []
    for filename, name, weight, regime, desc in universal_models:
        path = f"models/{filename}"
        if os.path.exists(path):
            if "Balanced" in name:
                feature_type = "universal"
            else:
                # Legacy Universal Fleet models use 52 features
                feature_type = "universal_v1"
            universal_configs.append(
                ModelConfig(
                    path=path,
                    name=name,
                    weight=weight,
                    regime=regime,
                    description=desc,
                    feature_type=feature_type,
                )
            )

    if universal_configs:
        print(
            f"✨ Found {len(universal_configs)} Universal Fleet models. Using them as primary."
        )
        # Return immediately if we have our specific universal fleet
        # We can mix in others if desired, but let's trust the fleet first.
        return EnsembleTrader(
            model_configs=universal_configs,
            strategy=EnsembleStrategy.REGIME_SPECIFIC
            if ("TQQQ" in symbol or "SQQQ" in symbol)
            else EnsembleStrategy.CONFIDENCE,
        )

    # 1. Symbol-Specific Ensemble Models (Legacy)
    # Weights rebalanced for more aggressive bull market behavior
    ensemble_types = [
        (
            "sharpe",
            "Sharpe",
            1.5,
            "bull",
            "Sharpe reward function",
        ),  # Increased, bullish
        (
            "sortino",
            "Sortino",
            0.8,
            "volatile",
            "Sortino reward (downside protection)",
        ),  # Reduced
        ("calmar", "Calmar", 1.0, "bear", "Calmar reward (drawdown focus)"),  # Reduced
        (
            "conservative",
            "Conservative",
            0.6,
            "sideways",
            "Low LR, high gamma",
        ),  # Reduced
        (
            "aggressive",
            "Aggressive",
            1.8,
            "bull",
            "High LR, low gamma",
        ),  # Increased, is for bull
        (
            "multi",
            "Multi-Symbol",
            1.8,
            "bull",
            "Multi-symbol training",
        ),  # Increased, bullish
        (
            "volume",
            "Volume_Expert",
            1.5,
            "all",
            "Volume/Microstructure Expert",
        ),  # New specialized model
    ]

    for type_key, type_name, weight, regime, desc in ensemble_types:
        # Try finding symbol-specific model first (e.g., TQQQ_ensemble_sharpe.zip)
        path = f"models/{symbol}_ensemble_{type_key}.zip"

        feature_type = "volume" if type_key == "volume" else "standard"

        if os.path.exists(path):
            model_configs.append(
                ModelConfig(
                    path=path,
                    name=f"{symbol} {type_name}",
                    weight=weight,
                    regime=regime,
                    description=desc,
                    feature_type=feature_type,
                )
            )
        elif symbol != "QQQ":
            # Fallback to QQQ models if symbol specific not found?
            # Maybe best not to mix unleveraged models with leveraged assets unless we are sure.
            # But for now, let's allow QQQ models as fallback if defined in original list.
            pass

    # 2. Add Hardcoded/Legacy Models (mostly QQQ based) if we are trading QQQ or just want robustness
    # Only add these if we are trading QQQ, or if we want to mix them in.
    # For TQQQ, we might want TQQQ specific models.

    if symbol == "QQQ":
        legacy_models = [
            ModelConfig(
                "models/trading_bot_QQQ_optimized.zip",
                "QQQ Bull",
                1.2,
                "bull",
                "Trained on full period",
            ),
            ModelConfig(
                "models/trading_bot_QQQ_bearish.zip",
                "QQQ Bear",
                1.5,
                "bear",
                "Trained on bear market",
            ),
            ModelConfig(
                "models/QQQ_10yr_sharpe.zip",
                "QQQ 10yr Sharpe",
                1.8,
                "bull",
                "10 years data, Sharpe reward",
            ),
        ]
        model_configs.extend([c for c in legacy_models if os.path.exists(c.path)])

    # 3. General Multi-Symbol Models (Applicable to all)
    # NOTE: Commented out because they use old feature set (39 features)
    # multi_path = "models/multi_symbol_sharpe.zip"
    # if os.path.exists(multi_path):
    #     model_configs.append(
    #         ModelConfig(
    #             path=multi_path,
    #             name="Multi-Symbol General",
    #             weight=1.0,
    #             regime=None,
    #             description="General QQQ/SPY/IWM model",
    #         )
    #     )

    # 4. Check for TQQQ specific legacy if exists
    # NOTE: Commented out because they use old feature set (39 features)
    # if symbol == "TQQQ":
    #     tqqq_path = "models/TQQQ_Sharpe.zip"
    #     if os.path.exists(tqqq_path):
    #         model_configs.append(
    #             ModelConfig(
    #                 path=tqqq_path,
    #                 name="TQQQ Sharpe Legacy",
    #                 weight=1.6,
    #                 regime=None,
    #                 description="10yr TQQQ Sharpe",
    #             )
    #         )

    # Filter to only existing models (double check)
    existing_configs = [c for c in model_configs if os.path.exists(c.path)]

    # If no models found, fallback to QQQ models as last resort
    if not existing_configs and symbol != "QQQ":
        print(f"⚠️ No specific models found for {symbol}. Falling back to QQQ models.")
        return create_default_ensemble("QQQ")

    # Select best strategy for symbol
    strategy = EnsembleStrategy.CONFIDENCE
    if "TQQQ" in symbol or "SQQQ" in symbol:
        print(f"⚡ Leveraged Token ({symbol}) detected: Using REGIME_SPECIFIC strategy")
        strategy = EnsembleStrategy.REGIME_SPECIFIC

    return EnsembleTrader(
        model_configs=existing_configs,
        strategy=strategy,
    )


if __name__ == "__main__":
    # Demo
    print("🎯 Ensemble Trading Demo\n")

    # Create ensemble
    ensemble = create_default_ensemble()

    # Print summary
    summary = ensemble.get_ensemble_summary()
    print(f"Loaded {summary['num_models']} models")
    print(f"Strategy: {summary['strategy']}")
    print("\nModels:")
    for m in summary["models"]:
        print(f"   {m['name']}: weight={m['weight']}, regime={m['regime']}")

    # Test with dummy observation
    print("\nTesting with dummy observation...")
    obs = np.random.randn(38).astype(np.float32)

    ensemble.print_prediction_analysis(obs, regime="bull")
