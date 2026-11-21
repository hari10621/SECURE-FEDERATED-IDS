#!/usr/bin/env python
# coding: utf-8

# In[3]:


#pip install shap


# In[4]:


import os
import random
import numpy as np
import pandas as pd
import tensorflow as tf
import shap
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from scipy.stats import spearmanr

# Reproducibility
SEED = 42
os.environ["PYTHONHASHSEED"] = str(SEED)
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

print("TensorFlow version:", tf.__version__)
print("SHAP version:", shap.__version__)


# In[12]:


DATA_PATH = "../Final_Binary_InSDN_Dataset.csv"


# In[ ]:





# In[13]:


MODEL_PATHS = {
    "4 clients": r"./4_InSDN_dkg_true/dkg_Federated_model_4.h5",
    "8 clients": r"./8_InSDN_dkg_true/dkg_Federated_model_4.h5",
    "12 clients": r"./12_InSDN_dkg_true/dkg_Federated_model_4.h5",
}


OUTPUT_DIR = r"\shap_stability_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

for name, path in MODEL_PATHS.items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"{name} model not found: {path}")

if not os.path.exists(DATA_PATH):
    raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

print("All files found.")


# In[14]:


df = pd.read_csv(DATA_PATH)

feature_names = df.columns[:-1].tolist()
label_name = df.columns[-1]

X = df.iloc[:, :-1].values.astype(np.float64)
y = df.iloc[:, -1].values.astype(np.int32)

print("Dataset shape:", df.shape)
print("Number of features:", len(feature_names))
print("Label column:", label_name)
print("Class distribution:")
print(pd.Series(y).value_counts().sort_index())

if len(feature_names) != 48:
    print(
        f"Warning: The dataset contains {len(feature_names)} features, "
        "whereas the expected model input contains 48 features."
    )

# Reproduce the preprocessing used in the training code
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled,
    y,
    test_size=0.30,
    random_state=42,
    stratify=y
)

# GRU input: samples × timesteps × features
X_train_gru = np.expand_dims(X_train, axis=1)
X_test_gru = np.expand_dims(X_test, axis=1)

print("Training input:", X_train_gru.shape)
print("Testing input:", X_test_gru.shape)


# In[15]:


def balanced_indices(y_values, total_samples, seed=42):
    """
    Select approximately equal numbers from every class.
    """
    rng = np.random.default_rng(seed)
    classes = np.unique(y_values)

    if total_samples < len(classes):
        raise ValueError("total_samples must be at least the number of classes.")

    base_count = total_samples // len(classes)
    selected = []

    for class_value in classes:
        class_indices = np.where(y_values == class_value)[0]

        if len(class_indices) < base_count:
            raise ValueError(
                f"Class {class_value} contains only {len(class_indices)} samples, "
                f"but {base_count} are required."
            )

        selected.extend(
            rng.choice(class_indices, size=base_count, replace=False)
        )

    selected = np.asarray(selected, dtype=int)
    rng.shuffle(selected)
    return selected


BACKGROUND_SIZE = 100
EXPLANATION_SIZE = 200

background_indices = balanced_indices(
    y_train,
    total_samples=BACKGROUND_SIZE,
    seed=42
)

explanation_indices = balanced_indices(
    y_test,
    total_samples=EXPLANATION_SIZE,
    seed=84
)

X_background = X_train_gru[background_indices]
X_explanation = X_test_gru[explanation_indices]
y_explanation = y_test[explanation_indices]

print("Background shape:", X_background.shape)
print("Explanation shape:", X_explanation.shape)
print("Explanation class counts:")
print(pd.Series(y_explanation).value_counts().sort_index())

# Save indices for reproducibility
np.savez(
    os.path.join(OUTPUT_DIR, "shap_stability_sample_indices.npz"),
    background_indices=background_indices,
    explanation_indices=explanation_indices
)


# In[16]:


models = {}

for model_name, model_path in MODEL_PATHS.items():
    model = tf.keras.models.load_model(
        model_path,
        compile=False
    )

    # Build and test the model in inference mode
    sample_output = model(X_background[:2], training=False)

    print(
        f"{model_name}: "
        f"input={model.input_shape}, "
        f"output={model.output_shape}, "
        f"sample prediction shape={sample_output.shape}"
    )

    expected_features = X_background.shape[-1]

    if model.input_shape[-1] != expected_features:
        raise ValueError(
            f"{model_name} expects {model.input_shape[-1]} features, "
            f"but the dataset contains {expected_features}."
        )

    models[model_name] = model


# In[17]:


def normalize_shap_array(raw_shap, n_samples, n_features):
    """
    Convert SHAP output into a two-dimensional array:
    samples × features.
    """
    if isinstance(raw_shap, list):
        # Binary single-output model commonly returns a one-item list
        raw_shap = raw_shap[0]

    if hasattr(raw_shap, "values"):
        raw_shap = raw_shap.values

    values = np.asarray(raw_shap)

    print("Raw SHAP shape:", values.shape)

    # Remove output dimensions of size 1
    values = np.squeeze(values)

    # Expected possibilities after squeezing:
    # (samples, features)
    # (samples, timesteps, features)
    if values.ndim == 2:
        pass

    elif values.ndim == 3:
        # Input has one timestep. Remove or average the timestep dimension.
        if values.shape[1] == 1:
            values = values[:, 0, :]
        else:
            values = np.mean(values, axis=1)

    else:
        raise ValueError(
            f"Unexpected SHAP shape after squeezing: {values.shape}"
        )

    if values.shape != (n_samples, n_features):
        raise ValueError(
            f"Normalized SHAP shape is {values.shape}; "
            f"expected {(n_samples, n_features)}."
        )

    return values


def calculate_global_shap(model, background, explanation_data):
    """
    Calculate sample-level SHAP values and global mean absolute importance.
    """
    explainer = shap.GradientExplainer(
        model,
        background
    )

    raw_shap = explainer.shap_values(
        explanation_data
    )

    shap_matrix = normalize_shap_array(
        raw_shap,
        n_samples=explanation_data.shape[0],
        n_features=explanation_data.shape[-1]
    )

    # Global feature importance
    mean_absolute_shap = np.mean(
        np.abs(shap_matrix),
        axis=0
    )

    return shap_matrix, mean_absolute_shap


# In[18]:


shap_matrices = {}
global_importances = {}

for model_name, model in models.items():
    print("\n" + "=" * 70)
    print("Calculating SHAP values for:", model_name)
    print("=" * 70)

    shap_matrix, importance = calculate_global_shap(
        model=model,
        background=X_background,
        explanation_data=X_explanation
    )

    shap_matrices[model_name] = shap_matrix
    global_importances[model_name] = importance

    np.save(
        os.path.join(
            OUTPUT_DIR,
            model_name.replace(" ", "_") + "_shap_values.npy"
        ),
        shap_matrix
    )

print("SHAP calculations completed.")


# In[19]:


def get_top_features(importance, feature_names, top_k=10):
    top_indices = np.argsort(importance)[::-1][:top_k]

    return pd.DataFrame({
        "Rank": np.arange(1, top_k + 1),
        "Feature index": top_indices,
        "Feature": [feature_names[i] for i in top_indices],
        "Mean absolute SHAP": importance[top_indices]
    })


top_feature_tables = {}

for model_name, importance in global_importances.items():
    table = get_top_features(
        importance,
        feature_names,
        top_k=10
    )

    top_feature_tables[model_name] = table

    print("\n", model_name)
    display(table)

    table.to_csv(
        os.path.join(
            OUTPUT_DIR,
            model_name.replace(" ", "_") + "_top10_features.csv"
        ),
        index=False
    )


# In[20]:


def compare_explanations(
    importance_a,
    importance_b,
    feature_names,
    top_k=10
):
    """
    Calculate:
    1. Spearman rank correlation
    2. Number of common top-k features
    3. Jaccard similarity
    """

    # Spearman correlation over all feature importance values
    rho, p_value = spearmanr(
        importance_a,
        importance_b
    )

    top_a_indices = set(
        np.argsort(importance_a)[::-1][:top_k]
    )
    top_b_indices = set(
        np.argsort(importance_b)[::-1][:top_k]
    )

    intersection = top_a_indices.intersection(top_b_indices)
    union = top_a_indices.union(top_b_indices)

    common_count = len(intersection)
    jaccard = common_count / len(union)

    # Sort common features by average importance
    common_sorted = sorted(
        intersection,
        key=lambda index: (
            importance_a[index] + importance_b[index]
        ) / 2,
        reverse=True
    )

    common_feature_names = [
        feature_names[index]
        for index in common_sorted
    ]

    return {
        "Spearman correlation": rho,
        "Spearman p-value": p_value,
        "Common top-10 features": common_count,
        "Jaccard similarity": jaccard,
        "Common feature names": ", ".join(common_feature_names)
    }


comparison_pairs = [
    ("4 clients", "8 clients"),
    ("4 clients", "12 clients"),
    ("8 clients", "12 clients")
]

comparison_rows = []

for first_model, second_model in comparison_pairs:
    comparison = compare_explanations(
        global_importances[first_model],
        global_importances[second_model],
        feature_names,
        top_k=10
    )

    comparison_rows.append({
        "Comparison": f"{first_model} vs. {second_model}",
        **comparison
    })

stability_results = pd.DataFrame(comparison_rows)

display(stability_results)


# In[21]:


manuscript_table = stability_results[
    [
        "Comparison",
        "Spearman correlation",
        "Common top-10 features",
        "Jaccard similarity"
    ]
].copy()

manuscript_table["Spearman correlation"] = (
    manuscript_table["Spearman correlation"].round(3)
)

manuscript_table["Jaccard similarity"] = (
    manuscript_table["Jaccard similarity"].round(3)
)

display(manuscript_table)

manuscript_table.to_csv(
    os.path.join(
        OUTPUT_DIR,
        "shap_stability_manuscript_table.csv"
    ),
    index=False
)

stability_results.to_csv(
    os.path.join(
        OUTPUT_DIR,
        "shap_stability_complete_results.csv"
    ),
    index=False
)


# In[22]:


importance_table = pd.DataFrame({
    "Feature": feature_names,
    "4 clients": global_importances["4 clients"],
    "8 clients": global_importances["8 clients"],
    "12 clients": global_importances["12 clients"]
})

importance_table["Mean importance"] = importance_table[
    ["4 clients", "8 clients", "12 clients"]
].mean(axis=1)

importance_table = importance_table.sort_values(
    "Mean importance",
    ascending=False
).reset_index(drop=True)

display(importance_table.head(15))

importance_table.to_csv(
    os.path.join(
        OUTPUT_DIR,
        "global_shap_importance_all_models.csv"
    ),
    index=False
)


# In[23]:


model_order = ["4 clients", "8 clients", "12 clients"]

correlation_matrix = np.eye(len(model_order))

for i in range(len(model_order)):
    for j in range(len(model_order)):
        rho, _ = spearmanr(
            global_importances[model_order[i]],
            global_importances[model_order[j]]
        )
        correlation_matrix[i, j] = rho

fig, ax = plt.subplots(figsize=(6, 5))

image = ax.imshow(
    correlation_matrix,
    vmin=-1,
    vmax=1
)

ax.set_xticks(range(len(model_order)))
ax.set_xticklabels(model_order)

ax.set_yticks(range(len(model_order)))
ax.set_yticklabels(model_order)

for i in range(len(model_order)):
    for j in range(len(model_order)):
        ax.text(
            j,
            i,
            f"{correlation_matrix[i, j]:.3f}",
            ha="center",
            va="center"
        )

ax.set_title("Spearman Correlation of Global SHAP Importance")
fig.colorbar(image, ax=ax, label="Spearman correlation")
plt.tight_layout()

figure_path = os.path.join(
    OUTPUT_DIR,
    "shap_stability_correlation_matrix.png"
)

plt.savefig(
    figure_path,
    dpi=300,
    bbox_inches="tight"
)

plt.show()


# In[ ]:




