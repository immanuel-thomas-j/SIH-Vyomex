import os
import pandas as pd
import numpy as np
import pickle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix, roc_auc_score, roc_curve
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import glob

# DISCLAIMER: SYNTHETIC dataset for ML pipeline development.
# This data does NOT represent real narcotics/explosives measurements.

LABEL_MAP = {'NORMAL': 0, 'UNKNOWN': 1, 'HIGH_RISK_SCREENING_EVENT': 2}
CLASS_NAMES = ['NORMAL', 'UNKNOWN', 'HIGH_RISK']
COLORS_MAP = {0: 'green', 1: 'orange', 2: 'red'}
COLORS_STR_MAP = {'NORMAL': 'green', 'UNKNOWN': 'orange', 'HIGH_RISK_SCREENING_EVENT': 'red'}

def evaluate():
    os.makedirs('plots', exist_ok=True)
    
    print("=== NARCOSCAN Baseline Evaluation Report ===")
    
    # Load all test prediction files
    pred_files = glob.glob('data/predictions/*_test.csv')
    models = [os.path.basename(f).replace('_test.csv', '') for f in pred_files]
    
    if not models:
        print("No predictions found in data/predictions/")
        return
        
    f1_scores = {'Model': [], 'Class': [], 'F1': []}
    
    for model, f in zip(models, pred_files):
        df = pd.read_csv(f)
        y_true = df['label'].map(LABEL_MAP).fillna(0).astype(int)
        y_pred = df['pred_class']
        
        acc = accuracy_score(y_true, y_pred)
        p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=[0,1,2], zero_division=0)
        
        cm = confusion_matrix(y_true, y_pred, labels=[0,1,2])
        fp_rate = cm[0, 2] / (cm[0].sum() + 1e-6)
        fn_rate = cm[2, 0] / (cm[2].sum() + 1e-6)
        
        print(f"\nModel: {model}")
        print(f"Accuracy: {acc:.4f}")
        for i, cname in enumerate(CLASS_NAMES):
            print(f"{cname:10s} - P: {p[i]:.4f}  R: {r[i]:.4f}  F1: {f1[i]:.4f}")
            f1_scores['Model'].append(model)
            f1_scores['Class'].append(cname)
            f1_scores['F1'].append(f1[i])
            
        print(f"FP Rate (NORMAL->HIGH_RISK): {fp_rate:.4f}")
        print(f"FN Rate (HIGH_RISK->NORMAL): {fn_rate:.4f}")
        
        # Plot Confusion Matrix
        plt.figure(figsize=(6,5))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=CLASS_NAMES, yticklabels=CLASS_NAMES)
        plt.title(f'{model} Confusion Matrix')
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        plt.tight_layout()
        plt.savefig(f'plots/{model}_cm.png')
        plt.close()

    # --- Confidence Threshold Analysis (Example for RandomForest) ---
    if 'RandomForest' in models:
        df_rf = pd.read_csv('data/predictions/RandomForest_test.csv')
        if 'prob_0' in df_rf.columns:
            thresholds = np.linspace(0.3, 0.95, 20)
            fprs, fnrs, rejections, accs = [], [], [], []
            y_t = df_rf['label'].map(LABEL_MAP).fillna(0).astype(int)
            probs = df_rf[['prob_0', 'prob_1', 'prob_2']].values
            
            for t in thresholds:
                max_p = np.max(probs, axis=1)
                pred_c = np.argmax(probs, axis=1)
                
                # Reject if confidence < t
                rejected = max_p < t
                pred_c[rejected] = 1 # Force to UNKNOWN
                
                cm = confusion_matrix(y_t, pred_c, labels=[0,1,2])
                fprs.append(cm[0, 2] / (cm[0].sum() + 1e-6))
                fnrs.append(cm[2, 0] / (cm[2].sum() + 1e-6))
                rejections.append(np.mean(rejected))
                
                accepted_mask = ~rejected
                if accepted_mask.sum() > 0:
                    accs.append(accuracy_score(y_t[accepted_mask], pred_c[accepted_mask]))
                else:
                    accs.append(0.0)
                    
            plt.figure(figsize=(8,6))
            plt.plot(thresholds, fprs, label='FPR (NORMAL->HIGH_RISK)')
            plt.plot(thresholds, fnrs, label='FNR (HIGH_RISK->NORMAL)')
            plt.plot(thresholds, rejections, label='Rejection Rate')
            plt.plot(thresholds, accs, label='Accuracy (Accepted)')
            plt.xlabel('Confidence Threshold')
            plt.ylabel('Rate / Accuracy')
            plt.title('Confidence Threshold Trade-offs (RandomForest)')
            plt.legend()
            plt.tight_layout()
            plt.savefig('plots/confidence_analysis.png')
            plt.close()

    # --- Feature plots ---
    try:
        train_df = pd.read_csv('data/train.csv')
        
        # 1. Feature Importance (if Random Forest exists)
        if os.path.exists('data/models/RandomForest.pkl') and os.path.exists('data/models/preprocessors.pkl'):
            with open('data/models/RandomForest.pkl', 'rb') as f:
                rf = pickle.load(f)
            with open('data/models/preprocessors.pkl', 'rb') as f:
                preproc = pickle.load(f)
                
            features = preproc.get('features', [])
            if features and hasattr(rf, 'feature_importances_'):
                importances = rf.feature_importances_
                idx = np.argsort(importances)[-15:] # Top 15
                
                plt.figure(figsize=(10,6))
                plt.barh(range(len(idx)), importances[idx], align='center')
                plt.yticks(range(len(idx)), [features[i] for i in idx])
                plt.xlabel('Feature Importance')
                plt.title('Top 15 Features (Random Forest)')
                plt.tight_layout()
                plt.savefig('plots/feature_importance.png')
                plt.close()

        # 2. PCA Visualization
        X_num = train_df.select_dtypes(include=[np.number]).dropna()
        y_label = train_df.loc[X_num.index, 'label']
        
        pca = PCA(n_components=2)
        X_pca = pca.fit_transform(X_num)
        
        plt.figure(figsize=(8,6))
        for lbl in train_df['label'].unique():
            mask = y_label == lbl
            plt.scatter(X_pca[mask, 0], X_pca[mask, 1], label=lbl, alpha=0.5, c=COLORS_STR_MAP.get(lbl, 'blue'))
        plt.xlabel('PCA 1')
        plt.ylabel('PCA 2')
        plt.legend()
        plt.title('PCA of Feature Space')
        plt.tight_layout()
        plt.savefig('plots/pca_visualization.png')
        plt.close()

        # 3. Class overlap
        if 'max_gas_response' in train_df.columns:
            plt.figure(figsize=(8,6))
            for lbl in train_df['label'].unique():
                sns.kdeplot(train_df[train_df['label'] == lbl]['max_gas_response'].dropna(), label=lbl, fill=True)
            plt.title('Class Overlap: Max Gas Response')
            plt.legend()
            plt.tight_layout()
            plt.savefig('plots/class_overlap.png')
            plt.close()

    except Exception as e:
        print(f"Error generating some feature plots: {e}")

if __name__ == '__main__':
    evaluate()
