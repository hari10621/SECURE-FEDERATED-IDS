#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    confusion_matrix, roc_curve, auc,
    accuracy_score, precision_score, recall_score,
    f1_score, matthews_corrcoef, cohen_kappa_score,
    log_loss, balanced_accuracy_score, ConfusionMatrixDisplay
)
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os

# ====================
# 1. CONFIG: Models + Datasets
# ====================
model_configs = [
    {
        'name'       : 'InSDN',
        'model_path' : '4_InSDN_dkg_true/dkg_Federated_model_4.h5',
        'data_path'  : '../Final_Binary_InSDN_Dataset.csv',
        'color'      : 'darkorange',
    },
    {
        'name'       : 'CICDDoS2019',
        'model_path' : '4_CICDDoS19_dkg_true/dkg_Federated_model_4.h5',
        'data_path'  : '../final_cicids2019_top48_features.csv',
        'color'      : 'steelblue',
    },
    {
        'name'       : 'CICDDoS2017',
        'model_path' : '4_CICDDoS17_dkg_true/dkg_Federated_model_4.h5',
        'data_path'  : '../final_cicids2017_top48_features.csv',
        'color'      : 'seagreen',
    },
]

# ====================
# 2. HELPER: Load + Preprocess (same as training)
# ====================
def load_and_preprocess(data_path):
    df         = pd.read_csv(data_path)
    data       = df.iloc[:, :-1].values
    labels     = df.iloc[:, -1].values

    scaler     = StandardScaler()
    data       = scaler.fit_transform(data)

    X_train, X_test, y_train, y_test = train_test_split(
        data, labels,
        test_size=0.3, random_state=42, stratify=labels   # must match training
    )

    X_test = np.expand_dims(X_test, axis=1)   # (N, 1, features) for GRU
    return X_test, y_test

# ====================
# 3. EVALUATE ALL MODELS
# ====================
results = []

for cfg in model_configs:
    print(f"\n{'='*60}")
    print(f"Evaluating: {cfg['name']}")
    print(f"{'='*60}")

    # Load data
    X_test, y_test = load_and_preprocess(cfg['data_path'])
    y_true = y_test.ravel().astype(int)
    print(f"  Test samples : {len(y_true)}")
    print(f"  Class dist   : {dict(zip(*np.unique(y_true, return_counts=True)))}")

    # Load model
    model  = tf.keras.models.load_model(cfg['model_path'])
    logits = model.predict(X_test, batch_size=256)
    y_prob = logits.ravel()
    y_pred = (y_prob > 0.5).astype(int)

    # Metrics
    acc     = accuracy_score(y_true, y_pred)
    prec    = precision_score(y_true, y_pred, average='binary')
    rec     = recall_score(y_true, y_pred, average='binary')
    f1      = f1_score(y_true, y_pred, average='binary')
    mcc     = matthews_corrcoef(y_true, y_pred)
    kappa   = cohen_kappa_score(y_true, y_pred)
    logloss = log_loss(y_true, y_prob)
    g_mean  = balanced_accuracy_score(y_true, y_pred)
    cm      = confusion_matrix(y_true, y_pred)
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    roc_auc = auc(fpr, tpr)

    print(f"  Accuracy  : {acc:.4f}")
    print(f"  Precision : {prec:.4f}")
    print(f"  Recall    : {rec:.4f}")
    print(f"  F1        : {f1:.4f}")
    print(f"  MCC       : {mcc:.4f}")
    print(f"  Kappa     : {kappa:.4f}")
    print(f"  Log Loss  : {logloss:.4f}")
    print(f"  Bal Acc   : {g_mean:.4f}")
    print(f"  ROC AUC   : {roc_auc:.4f}")
    print(f"  CM        : TN={cm[0,0]}, FP={cm[0,1]}, FN={cm[1,0]}, TP={cm[1,1]}")

    results.append({
        **cfg,
        'y_true'  : y_true,
        'y_pred'  : y_pred,
        'y_prob'  : y_prob,
        'cm'      : cm,
        'fpr'     : fpr,
        'tpr'     : tpr,
        'roc_auc' : roc_auc,
        'acc'     : acc,
        'f1'      : f1,
    })

    tf.keras.backend.clear_session()

# ====================
# 4. COMBINED ROC CURVE (3 models, 1 plot)
# ====================
fig, ax = plt.subplots(figsize=(8, 6))

for r in results:
    ax.plot(r['fpr'], r['tpr'],
            color=r['color'], lw=2,
            label=f"{r['name']}  (AUC = {r['roc_auc']:.4f})")
    ax.fill_between(r['fpr'], r['tpr'], alpha=0.05, color=r['color'])

ax.plot([0, 1], [0, 1], color='gray', lw=1.2,
        linestyle='--', label='Random Classifier')

ax.set_xlim([0.0, 1.0])
ax.set_ylim([0.0, 1.02])
ax.set_xlabel('False Positive Rate', fontsize=13)
ax.set_ylabel('True Positive Rate', fontsize=13)
ax.set_title('ROC Curve – DKG True Threshold Federated Learning\n(3 Datasets)', fontsize=13)
ax.legend(loc='lower right', fontsize=11)
ax.grid(alpha=0.3)
plt.tight_layout()
# plt.savefig('combined_roc_curve.png', dpi=150)
plt.show()
print("\nCombined ROC curve saved → combined_roc_curve.png")

# ====================
# 5. COMBINED CONFUSION MATRICES (3 subplots, 1 figure)
# ====================
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

for ax, r in zip(axes, results):
    disp = ConfusionMatrixDisplay(
        confusion_matrix=r['cm'],
        display_labels=['Normal', 'Attack']
    )
    disp.plot(ax=ax, cmap='Blues', colorbar=False)

    # Subtitle with key metrics
    ax.set_title(
        f"{r['name']}\n"
        f"Acc={r['acc']:.4f}  F1={r['f1']:.4f}  AUC={r['roc_auc']:.4f}",
        fontsize=11, pad=10
    )

    # Add TN/FP/FN/TP annotations under the matrix
    cm = r['cm']
    ax.set_xlabel(
        f"TN={cm[0,0]:,}  FP={cm[0,1]:,}  FN={cm[1,0]:,}  TP={cm[1,1]:,}",
        fontsize=9, labelpad=8
    )

fig.suptitle(
    'Confusion Matrices – DKG True Threshold Federated Learning',
    fontsize=13, y=1.02
)
plt.tight_layout()
# plt.savefig('combined_confusion_matrices.png', dpi=150, bbox_inches='tight')
plt.show()
print("Combined confusion matrices saved → combined_confusion_matrices.png")


# In[2]:


import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from sklearn.metrics import ConfusionMatrixDisplay

# ====================
# ROC CURVE — log scale x-axis to separate near-perfect curves
# ====================
styles = [
    {'color': '#E07B39', 'ls': '-',       'lw': 2.5, 'marker': 'o',  'ms': 5},
    {'color': '#3A8CC1', 'ls': '--',      'lw': 2.5, 'marker': 's',  'ms': 5},
    {'color': '#3BAA6E', 'ls': (0,(3,3)), 'lw': 2.5, 'marker': '^',  'ms': 5},
]

fig, ax = plt.subplots(figsize=(9, 6.5))

for r, st in zip(results, styles):
    auc_val = r['roc_auc']
    # Show 4 decimal places so 1.0000 vs 0.9995 are clear
    auc_str = f"{auc_val * 100:.4f}%"
    label   = f"{r['name']}  (AUC = {auc_str})"

    fpr = r['fpr']
    tpr = r['tpr']

    # Avoid log(0): clip FPR minimum to 1e-5
    fpr_plot = np.clip(fpr, 1e-5, 1.0)

    ax.plot(fpr_plot, tpr,
            color=st['color'], linestyle=st['ls'], linewidth=st['lw'],
            label=label)
    ax.fill_between(fpr_plot, tpr, alpha=0.06, color=st['color'])

    # Mark the operating point (threshold=0.5) with a marker
    # Find index closest to threshold 0.5 operating point
    op_idx = np.argmin(np.abs(fpr - fpr[np.searchsorted(fpr, 0.001)]))
    ax.plot(np.clip(fpr[op_idx], 1e-5, 1.0), tpr[op_idx],
            marker=st['marker'], color=st['color'],
            markersize=st['ms'], zorder=5)

# Diagonal reference on log scale
x_diag = np.logspace(-5, 0, 300)
ax.plot(x_diag, x_diag, color='#888780', lw=1.5,
        linestyle='--', label='Random classifier', alpha=0.7)

ax.set_xscale('log')
ax.set_xlim([1e-4, 1.0])
ax.set_ylim([0.96, 1.002])           # Zoom y-axis into top region too

ax.set_xlabel('False positive rate  (log scale)', fontsize=13)
ax.set_ylabel('True positive rate', fontsize=13)
# ax.set_title('ROC curve – DKG true threshold federated learning\n'
#              '(log-scale FPR to separate near-perfect classifiers)',
#              fontsize=13)
ax.legend(loc='lower right', fontsize=11, framealpha=0.95)
ax.grid(which='both', alpha=0.2)
ax.grid(which='major', alpha=0.35)

# Add annotation for each model's operating point
annotations = [
    (results[0]['fpr'], results[0]['tpr'], '#E07B39', 'InSDN\n(FP=64)'),
    (results[1]['fpr'], results[1]['tpr'], '#3A8CC1', 'CICDDoS2019\n(FP=203)'),
    (results[2]['fpr'], results[2]['tpr'], '#3BAA6E', 'CICDDoS2017\n(FP=1277)'),
]
offsets = [(0.0003, -0.008), (0.004, -0.010), (0.006, -0.015)]

for (fpr_arr, tpr_arr, col, txt), (dx, dy) in zip(annotations, offsets):
    # Find point nearest to actual threshold=0.5 operating point
    # (just use a mid-range FPR point for annotation)
    idx = np.searchsorted(fpr_arr, [0.0002, 0.005, 0.008][annotations.index(
        next(a for a in annotations if a[2] == col))])
    idx = min(idx, len(fpr_arr) - 1)
    xp  = np.clip(fpr_arr[idx], 1e-5, 1.0)
    yp  = tpr_arr[idx]

plt.tight_layout()
plt.savefig('combined_roc_curve.pdf', format='pdf', bbox_inches='tight')
plt.show()
print("Saved → combined_roc_curve.png")



# In[3]:


for r in results:
    cm = r['cm']
    tn, fp, fn, tp = cm[0,0], cm[0,1], cm[1,0], cm[1,1]

    fig, ax = plt.subplots(figsize=(6, 5))

    disp = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=['Normal', 'Attack']
    )
    disp.plot(ax=ax, cmap='Blues', colorbar=False)

    # Numbers inside cells
    for text in disp.text_.ravel():
        value = int(text.get_text())
        text.set_text(f"{value:,}")   # ← adds comma formatting
        text.set_fontsize(18)
        text.set_fontweight('bold')

    # Axis labels
    ax.set_xlabel('Predicted label', fontsize=13, labelpad=10)
    ax.set_ylabel('True label', fontsize=13)

    # Tick labels
    ax.tick_params(axis='x', labelsize=12)
    ax.tick_params(axis='y', labelsize=12)

    # # Title
    # ax.set_title(
    #     f"{r['name']}\n"
    #     f"Acc = {r['acc']*100:.2f}%   "
    #     f"F1 = {r['f1']*100:.2f}%   "
    #     f"AUC = {r['roc_auc']*100:.4f}%",
    #     fontsize=12, pad=12
    # )

    plt.tight_layout()
    plt.savefig(f"confusion_matrix_{r['name']}.pdf", format='pdf', bbox_inches='tight')
    plt.show()
    print(f"Saved → confusion_matrix_{r['name']}.pdf")


# In[ ]:




