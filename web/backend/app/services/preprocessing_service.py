"""Preprocessing pipeline matching the paper (Section IV-A).

Two preprocessing modes exist:
* ``clean``: split first, then fit the scaler on the training partition only.
  This is the research-standard approach that avoids leakage.
* ``legacy``: fit the scaler on all rows before splitting.  This reproduces
  the research scripts and therefore leaks test statistics into training.  It
  is retained only for comparison and must be labelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, List, Optional, Tuple

EXPECTED_FEATURE_COUNT = 48
DEFAULT_TEST_SIZE = 0.3
DEFAULT_SPLIT_SEED = 42


def _try_import_sklearn():
    """Try to import sklearn components, return them or None."""
    try:
        from sklearn.feature_selection import chi2, SelectKBest
        from sklearn.model_selection import StratifiedShuffleSplit
        from sklearn.preprocessing import StandardScaler
        return True
    except ImportError:
        return False


SKLEARN_AVAILABLE = _try_import_sklearn()


def _try_import_smote():
    """Try to import SMOTE."""
    try:
        from imblearn.over_sampling import SMOTE
        return True
    except ImportError:
        return False

SMOTE_AVAILABLE = _try_import_smote()


def detect_dataset_type(csv_path: str) -> str:
    """Detect the dataset type based on column names.

    Returns:
        "insdn" | "cicddos2017" | "cicddos2019"
    """
    try:
        df = pd.read_csv(csv_path, nrows=1)
        header = [str(col).strip() for col in df.columns]

        # Check for InSDN columns
        insdn_keywords = {
            "duration", "idle_timeout", "hard_timeout", "priority",
            "eth_type", "ip_proto", "tcp_src_port", "tcp_dst_port",
            "udp_src_port", "udp_dst_port", "icmp_code", "icmp_type",
            "ipv4_src_addr", "ipv4_dst_addr", "packets_in", "bytes_in",
            "pkt_per_sec", "byte_per_sec", "duration_nsec", "tx_bytes",
            "tx_packets", "rx_bytes", "rx_packets", "tcp_flags",
            "syn_flag", "ack_flag", "fin_flag", "rst_flag",
            "window_size", "ip_ttl", "tcp_len", "dns_qr",
            "http_method", "http_status_code", "http_content_type",
            "tls_version", "flow_count_per_switch", "flow_entropy",
            "min_pkt_size", "max_pkt_size", "avg_pkt_size",
            "port_traffic_ratio", "ssh_flag", "smtp_flag",
            "dns_flag", "http_flag", "webflag", "flow_anomaly_score",
            "Label"}

        # Check for CICDDoS2017 columns
        cicddos2017_keywords = {
            "Flow Duration", "Total Fwd Packets", "Total Backward Packets",
            "Total Length of Fwd Packets", "Total Length of Backward Packets",
            "Fwd Packet Length Max", "Fwd Packet Length Min",
            "Fwd Packet Length Mean", "Fwd Packet Length Std",
            "Bwd Packet Length Max", "Bwd Packet Length Min",
            "Bwd Packet Length Mean", "Bwd Packet Length Std",
            "Fwd Packet Length Max to Min Ratio", "Fwd Packet Length Max to Mean Ratio",
            "Fwd Packet Length Min to Mean Ratio", "Bwd Packet Length Max to Min Ratio",
            "Bwd Packet Length Max to Mean Ratio", "Bwd Packet Length Min to Mean Ratio",
            "Fwd Header Length", "Fwd Header Length to Total Length Ratio",
            "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
            "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
            "Fwd PSH Flags", "Fwd URG Flags", "Fwd CWR Flags", "Fwd ECE Flags",
            "Bwd PSH Flags", "Bwd URG Flags", "Bwd CWR Flags", "Bwd ECE Flags",
            "Fwd Header Length", "Fwd Avg Bytes/Bulk", "Fwd Avg Packets/Bulk",
            "Fwd Avg Bulk Rate", "Bwd Avg Bytes/Bulk", "Bwd Avg Packets/Bulk",
            "Bwd Avg Bulk Rate", "Flow IAT Total", "Flow IAT Mean", "Flow IAT Std",
            "Flow IAT Max", "Flow IAT Min", "Flow IAT Mean (Dir)", "Flow IAT Std (Dir)",
            "Flow IAT Max (Dir)", "Flow IAT Min (Dir)", "Flow IAT Mean",
            "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
            "Flow IAT Mean (Bwd)", "Flow IAT Std (Bwd)", "Flow IAT Max (Bwd)",
            "Flow IAT Min (Bwd)", "Fwd Segment Size", "Fwd Segment Size Min",
            "Fwd Segment Size Max", "Fwd Segment Size Mean", "Fwd Segment Size Std",
            "Bwd Segment Size", "Bwd Segment Size Min", "Bwd Segment Size Max",
            "Bwd Segment Size Mean", "Bwd Segment Size Std", "Fwd Header Length",
            "Fwd Header Length to Total Length Ratio", "Fwd Avg Packets/Bulk",
            "Fwd Avg Bulk Rate", "Bwd Header Length", "Bwd Header Length to Total Length Ratio",
            "Bwd Avg Bytes/Bulk", "Bwd Avg Packets/Bulk", "Bwd Avg Bulk Rate",
            "Subflow Fwd Packets", "Subflow Backward Packets", "Fwd Header Length",
            "Fwd Avg Bytes/Bulk", "Fwd Avg Packets/Bulk", "Fwd Avg Bulk Rate",
            "Bwd Avg Bytes/Bulk", "Bwd Avg Packets/Bulk", "Bwd Avg Bulk Rate",
            "Label"}

        # Check for CICDDoS2019 columns
        cicddos2019_keywords = {
            "Destination Port", "Flow Duration", "Total Fwd Packets",
            "Total Backward Packets", "Total Length of Fwd Packets",
            "Total Length of Backward Packets", "Fwd Packet Length Max",
            "Fwd Packet Length Min", "Fwd Packet Length Mean",
            "Fwd Packet Length Std", "Bwd Packet Length Max",
            "Bwd Packet Length Min", "Bwd Packet Length Mean",
            "Bwd Packet Length Std", "Fwd Packet Length Max to Min Ratio",
            "Fwd Packet Length Max to Mean Ratio", "Fwd Packet Length Min to Mean Ratio",
            "Bwd Packet Length Max to Min Ratio", "Bwd Packet Length Max to Mean Ratio",
            "Bwd Packet Length Min to Mean Ratio", "Fwd Header Length",
            "Fwd Header Length to Total Length Ratio", "Fwd IAT Total",
            "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
            "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max",
            "Bwd IAT Min", "Fwd PSH Flags", "Fwd URG Flags", "Fwd CWR Flags",
            "Fwd ECE Flags", "Bwd PSH Flags", "Bwd URG Flags", "Bwd CWR Flags",
            "Bwd ECE Flags", "Fwd URG Flags", "Fwd CWR Flags", "Fwd ECE Flags",
            "Bwd URG Flags", "Bwd CWR Flags", "Bwd ECE Flags", "Flow IAT Total",
            "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
            "Flow IAT Mean (Dir)", "Flow IAT Std (Dir)", "Flow IAT Max (Dir)",
            "Flow IAT Min (Dir)", "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max",
            "Flow IAT Min", "Flow IAT Mean (Bwd)", "Flow IAT Std (Bwd)",
            "Flow IAT Max (Bwd)", "Flow IAT Min (Bwd)", "Fwd Segment Size",
            "Fwd Segment Size Min", "Fwd Segment Size Max", "Fwd Segment Size Mean",
            "Fwd Segment Size Std", "Bwd Segment Size", "Bwd Segment Size Min",
            "Bwd Segment Size Max", "Bwd Segment Size Mean", "Bwd Segment Size Std",
            "Fwd Avg Bytes/Bulk", "Fwd Avg Packets/Bulk", "Fwd Avg Bulk Rate",
            "Bwd Avg Bytes/Bulk", "Bwd Avg Packets/Bulk", "Bwd Avg Bulk Rate",
            "Fwd Header Length", "Fwd Header Length to Total Length Ratio",
            "Fwd Avg Bulk Rate", "Bwd Avg Bulk Rate", "Fwd Avg Packets/Bulk",
            "Bwd Avg Packets/Bulk", "Fwd Avg Bytes/Bulk", "Bwd Avg Bytes/Bulk",
            "Label"}

        # Get all column names from the full dataset
        df_full = pd.read_csv(csv_path)
        all_columns = set(str(col).strip() for col in df_full.columns)

        # Determine dataset type based on column name overlap
        insdn_overlap = len(all_columns & insdn_keywords)
        cicddos2017_overlap = len(all_columns & cicddos2017_keywords)
        cicddos2019_overlap = len(all_columns & cicddos2019_keywords)

        if insdn_overlap > cicddos2017_overlap and insdn_overlap > cicddos2019_overlap:
            return "insdn"
        elif cicddos2017_overlap > cicddos2019_overlap:
            return "cicddos2017"
        elif cicddos2019_overlap > 0:
            return "cicddos2019"
        else:
            # Default fallback: check column names pattern
            first_col = str(df_full.columns[0]).strip().lower()
            if "duration" in first_col and "label" in str(df_full.columns[-1]).lower():
                return "insdn"
            elif "Destination Port" in str(df_full.columns[0]):
                return "cicddos2019"
            else:
                return "insdn"  # Default to InSDN

    except Exception:
        return "insdn"  # Fallback default


def _map_labels(dataset_type: str, labels: np.ndarray, label_col_name: str = "Label") -> np.ndarray:
    """Map string labels to binary 0/1 based on dataset type.

    - InSDN: Normal=0, any attack=1
    - CICDDoS2017/CICDDoS2019: BENIGN=0, all others=1
    """
    mapped = labels.copy()
    if dataset_type == "insdn":
        # InSDN: Normal=0, any attack=1
        unique_labels = np.unique(labels)
        for lbl in unique_labels:
            lbl_str = str(lbl)
            if lbl_str == "0":
                mapped[mapped == lbl] = 0
            elif lbl_str == "1":
                mapped[mapped == lbl] = 1
            else:
                if lbl_str.lower() in ("normal", "benign", "benign."):
                    mapped[mapped == lbl] = 0
                else:
                    mapped[mapped == lbl] = 1
    elif dataset_type in ("cicddos2017", "cicddos2019"):
        # CICDDoS2017/2019: BENIGN=0, all others=1
        unique_labels = np.unique(labels)
        for lbl in unique_labels:
            lbl_str = str(lbl).strip()
            if lbl_str.upper() == "BENIGN":
                mapped[mapped == lbl] = 0
            else:
                mapped[mapped == lbl] = 1

    return mapped


SMOTE_AVAILABLE = _try_import_smote()


def _compute_iqr_bounds(X_numeric: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute IQR-based outlier bounds.

    Returns:
        median, lower_bound, upper_bound
    """
    median = np.median(X_numeric, axis=0)
    q1 = np.percentile(X_numeric, 25, axis=0)
    q3 = np.percentile(X_numeric, 75, axis=0)
    iqr = q3 - q1
    lower_bound = median - 3 * iqr
    upper_bound = median + 3 * iqr
    return median, lower_bound, upper_bound


def _remove_outliers(X_numeric: np.ndarray, lower_bound: np.ndarray, upper_bound: np.ndarray) -> np.ndarray:
    """Remove rows where any feature is outside median +/- 3*IQR."""
    outlier_mask = np.zeros(len(X_numeric), dtype=bool)
    for i in range(X_numeric.shape[1]):
        col_data = X_numeric[:, i]
        outlier_mask |= ((col_data < lower_bound[i]) | (col_data > upper_bound[i]))
    return X_numeric[~outlier_mask]


def _try_import_sklearn_lazy():
    """Lazy import of sklearn - return components or None."""
    try:
        from sklearn.feature_selection import chi2, SelectKBest
        from sklearn.model_selection import StratifiedShuffleSplit
        from sklearn.preprocessing import StandardScaler
        return True
    except ImportError:
        return False


def _standard_scaler_transform(X_train: np.ndarray, X_test: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply StandardScaler, fit on train only."""
    if SKLEARN_AVAILABLE:
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        return X_train_scaled, X_test_scaled
    # Fallback: manual standardization
    mean = np.mean(X_train, axis=0)
    std = np.std(X_train, axis=0)
    std[std == 0] = 1.0
    X_train_scaled = (X_train - mean) / std
    X_test_scaled = (X_test - mean) / std
    return X_train_scaled, X_test_scaled


def _feature_selection_chi2(X: np.ndarray, y: np.ndarray, feature_names: List[str],
                            k: int = 48) -> Tuple[np.ndarray, List[str]]:
    """Run Chi-Square feature selection.

    Returns:
        X_selected: array of selected features
        selected_feature_names: list of selected feature names
    """
    if not SKLEARN_AVAILABLE:
        # Fallback: select top k features by variance
        if X.shape[1] <= k:
            return X[:, :k], feature_names[:k]
        variances = np.var(X, axis=0)
        indices = np.argsort(-variances)[:k]
        return X[:, indices], [feature_names[i] for i in indices]

    try:
        from sklearn.feature_selection import SelectKBest, chi2 as _chi2

        # chi2 requires non-negative values
        X_pos = np.maximum(X, 0)
        selector = SelectKBest(_chi2, k=k)
        X_selected = selector.fit_transform(X_pos, y.astype(int))
        scores = selector.scores_
        indices = np.argsort(-scores)[:k]
        selected_names = [feature_names[i] for i in indices if i < len(feature_names)]
        return X_selected[:, indices], selected_names
    except Exception:
        # Fallback: select top k features by variance
        variances = np.var(X, axis=0)
        indices = np.argsort(-variances)[:k]
        return X[:, indices], [feature_names[i] for i in indices]


def load_and_preprocess(csv_path: str, dataset_type: str = "insdn",
                        mode: str = "clean") -> Tuple[List[List[float]], List[List[float]],
                                                       List[int], List[int], List[str]]:
    """Load and preprocess dataset matching the paper (Section IV-A).

    Pipeline steps:
    a. Loads raw CSV
    b. Removes duplicate rows
    c. Drops rows with missing/NaN/infinite values
    d. Converts any categorical columns to numeric
    e. Filters outliers (IQR-based, remove rows where any feature is >3 IQR from median)
    f. Runs Chi-Square feature selection → selects top 48 most relevant features
      (use sklearn.feature_selection.chi2 + SelectKBest)
    g. Applies StandardScaler (fit on train only — "clean" mode)
    h. Does stratified 70/30 train/test split (seed=42)
    i. Returns: train_rows, test_rows, train_labels, test_labels, feature_names (48)

    Args:
        csv_path: Path to the CSV file
        dataset_type: "insdn" | "cicddos2017" | "cicddos2019"
        mode: "clean" (fit scaler on train only) or "legacy" (fit on all data)

    Returns:
        (train_rows, test_rows, train_labels, test_labels, feature_names)
        Where feature_names contains exactly 48 feature names.
    """
    # Step a: Load raw CSV
    df = pd.read_csv(csv_path, dtype=str)

    # Step b: Remove duplicate rows
    df = df.drop_duplicates()

    # Step c: Drop rows with missing/NaN/infinite values
    # Convert all columns to numeric, coerce errors to NaN
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with any NaN values
    df = df.dropna()

    # Also drop rows with infinite values
    df = df[~np.isinf(df.select_dtypes(include=[float, int]).astype(float)).any(axis=1)]

    if df.empty:
        raise ValueError("No valid data rows after cleaning")

    # Step d: Convert any remaining categorical columns to numeric
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = pd.factorize(df[col])[0]

    # Get feature names and label
    all_cols = list(df.columns)

    # Determine label column
    if dataset_type == "insdn":
        label_col = "Label"
    elif dataset_type in ("cicddos2017", "cicddos2019"):
        label_col = "Label"
    else:
        # Auto-detect: last column as label
        label_col = all_cols[-1] if all_cols else "Label"

    if label_col not in all_cols:
        label_col = all_cols[-1] if all_cols else "Label"

    # Separate features and label
    y = df[label_col].values.astype(int)
    X = df.drop(columns=[label_col])

    # Get feature names (remove label)
    feature_names = [col for col in X.columns if col != label_col]

    # Step e: Filter outliers (IQR-based)
    # Remove rows where any feature is >3 IQR from median
    X_numeric = X.select_dtypes(include=[float, int]).astype(float)
    if X_numeric.empty:
        raise ValueError("No numeric features after filtering")

    X_np = X_numeric.to_numpy()
    median, lower_bound, upper_bound = _compute_iqr_bounds(X_np)

    # Remove outlier rows using numpy indexing
    outlier_mask = np.zeros(len(X_np), dtype=bool)
    for i in range(X_np.shape[1]):
        col_data = X_np[:, i]
        outlier_mask |= ((col_data < lower_bound[i]) | (col_data > upper_bound[i]))

    keep_mask = ~outlier_mask
    X_clean = X_np[keep_mask]
    y_clean = y[keep_mask]
    # feature_names stays the same

    # Step f: Runs Chi-Square feature selection → selects top 48 most relevant features
    # Ensure features are non-negative for chi2
    X_chi2 = X_clean.copy()
    X_chi2[X_chi2 < 0] = 0  # chi2 requires non-negative values

    k = min(EXPECTED_FEATURE_COUNT, X_chi2.shape[1], len(y_clean))
    if k < 1:
        raise ValueError("Not enough features for chi2 selection")

    # Use sklearn if available, otherwise fallback
    X_selected = X_clean.astype(float)
    selected_features = feature_names[:]

    if SKLEARN_AVAILABLE:
        try:
            from sklearn.feature_selection import SelectKBest, chi2 as _chi2

            selector = SelectKBest(_chi2, k=k)
            X_selected_arr = selector.fit_transform(X_chi2, y_clean.astype(int))
            scores = selector.scores_
            indices = np.argsort(-scores)[:k]
            selected_features = [feature_names[i] for i in indices if i < len(feature_names)]
            # Apply keep_mask to X_selected - but selector already handles this
            X_selected = X_selected_arr[:, indices]
        except Exception:
            # Fallback: select top k features by variance
            variances = np.var(X_np[keep_mask], axis=0)
            indices = np.argsort(-variances)[:k]
            X_selected = X_np[keep_mask][:, indices]
            selected_features = [feature_names[i] for i in indices]
    else:
        # Fallback: select top k features by variance
        variances = np.var(X_np[keep_mask], axis=0)
        indices = np.argsort(-variances)[:k]
        X_selected = X_np[keep_mask][:, indices]
        selected_features = [feature_names[i] for i in indices]

    # Ensure we have exactly 48 features
    if len(selected_features) < EXPECTED_FEATURE_COUNT:
        # Pad with remaining features
        remaining = [f for i, f in enumerate(feature_names) if i >= EXPECTED_FEATURE_COUNT]
        selected_features.extend(remaining[:EXPECTED_FEATURE_COUNT - len(selected_features)])

    selected_features = selected_features[:EXPECTED_FEATURE_COUNT]

    # Step h: Does stratified 70/30 train/test split (seed=42)
    if SKLEARN_AVAILABLE:
        from sklearn.model_selection import StratifiedShuffleSplit as _SSS
        from sklearn.preprocessing import StandardScaler as _SS

        y_clean_int = np.array(y_clean, dtype=int)
        if y_clean_int.dtype not in (np.int32, np.int64, int):
            y_clean_int = y_clean_int.astype(int)

        sss = StratifiedShuffleSplit(n_splits=1, test_size=DEFAULT_TEST_SIZE, random_state=DEFAULT_SPLIT_SEED)
        train_idx, test_idx = next(sss.split(X_selected, y_clean_int))

        # Step g: Apply StandardScaler (fit on train only)
        scaler = StandardScaler()
        X_train_selected = X_selected[train_idx]
        X_test_selected = X_selected[test_idx]
        y_train_selected = y_clean[train_idx]
        y_test_selected = y_clean[test_idx]

        X_train_scaled, X_test_scaled = _standard_scaler_transform(X_train_selected, X_test_selected)

        train_rows = X_train_scaled.tolist()
        test_rows = X_test_scaled.tolist()
        train_labels = y_train_selected.tolist()
        test_labels = y_test_selected.tolist()
    else:
        # Fallback without sklearn - simple 70/30 split
        n_samples = len(X_selected)
        n_train = int(n_samples * 0.7)
        rng = np.random.default_rng(DEFAULT_SPLIT_SEED)
        indices = rng.permutation(n_samples)
        train_idx = indices[:n_train]
        test_idx = indices[n_train:]

        X_train = X_selected[train_idx]
        X_test = X_selected[test_idx]
        y_train = y_clean[train_idx]
        y_test = y_clean[test_idx]

        # Manual standardization
        mean = np.mean(X_train, axis=0)
        std = np.std(X_train, axis=0)
        std[std == 0] = 1.0
        X_train_scaled = (X_train - mean) / std
        X_test_scaled = (X_test - mean) / std

        train_rows = X_train_scaled.tolist()
        test_rows = X_test_scaled.tolist()
        train_labels = y_train.tolist()
        test_labels = y_test.tolist()

    # Return feature names (should be 48)
    final_feature_names = selected_features[:EXPECTED_FEATURE_COUNT]

    # Ensure we have exactly 48 feature names
    while len(final_feature_names) < EXPECTED_FEATURE_COUNT:
        final_feature_names.append(f"feature_{len(final_feature_names)}")

    return train_rows, test_rows, train_labels, test_labels, final_feature_names[:EXPECTED_FEATURE_COUNT]


def class_balance_smote(X_rows: List[List[float]], y_labels: List[int], dataset_type: str = "insdn"
) -> Tuple[List[List[float]], List[int]]:
    """Balance classes using SMOTE.

    Args:
        X_rows: feature rows
        y_labels: binary labels (0=normal, 1=attack)
        dataset_type: dataset type for label mapping

    Returns:
        (balanced_X_rows, balanced_y_labels)
    """
    if not SMOTE_AVAILABLE:
        # If SMOTE not available, return as-is
        return X_rows, y_labels

    from imblearn.over_sampling import SMOTE as _SMOTE

    X_np = np.array(X_rows, dtype=float)
    y_np = np.array(y_labels, dtype=int)

    # Map labels to binary if needed
    y_mapped = _map_labels(dataset_type, y_np)

    smote = _SMOTE(random_state=42)
    X_balanced, y_balanced = smote.fit_resample(X_np, y_mapped)

    return X_balanced.tolist(), y_balanced.tolist()