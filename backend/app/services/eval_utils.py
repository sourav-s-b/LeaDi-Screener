"""
eval_utils.py
Shared evaluation helpers — compute standard classification metrics
from y_true / y_score arrays without assuming any specific model type.
"""
from __future__ import annotations
import numpy as np
from app.models.schemas import EvalReport


def compute_eval_report(y_true: np.ndarray, y_score: np.ndarray) -> EvalReport:
    """
    Parameters
    ----------
    y_true  : 1-D int array, 0 = negative, 1 = positive
    y_score : 1-D float array, predicted probability of positive class

    Returns
    -------
    EvalReport with accuracy, sensitivity, specificity, ROC-AUC, PR-AUC,
    confusion matrix, and sample count.
    """
    from sklearn.metrics import (
        roc_auc_score, average_precision_score,
        confusion_matrix,
    )

    y_pred = (y_score >= 0.5).astype(int)
    n      = len(y_true)

    accuracy = float(np.mean(y_pred == y_true))

    cm = confusion_matrix(y_true, y_pred)
    # cm shape: [[TN, FP], [FN, TP]]
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, n)

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    try:
        roc_auc = float(roc_auc_score(y_true, y_score))
    except ValueError:
        roc_auc = 0.0

    try:
        pr_auc = float(average_precision_score(y_true, y_score))
    except ValueError:
        pr_auc = 0.0

    return EvalReport(
        accuracy=round(accuracy, 4),
        sensitivity=round(sensitivity, 4),
        specificity=round(specificity, 4),
        roc_auc=round(roc_auc, 4),
        pr_auc=round(pr_auc, 4),
        conf_matrix=cm.tolist(),
        n_samples=n,
    )
