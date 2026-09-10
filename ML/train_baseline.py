import os
import pandas as pd
import numpy as np
import pickle
import warnings
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

# DISCLAIMER: SYNTHETIC dataset for ML pipeline development.
# This data does NOT represent real narcotics/explosives measurements.

warnings.filterwarnings('ignore')

LABEL_MAP = {'NORMAL': 0, 'UNKNOWN': 1, 'HIGH_RISK_SCREENING_EVENT': 2}
META_COLS = ['event_id', 'session_id', 'device_id', 'label', 'synthetic_condition', 
             'anomaly_strength', 'environmental_condition', 'simulated_event_type']

class RuleBasedBaseline:
    def __init__(self):
        self.threshold_high = 0.6
        self.threshold_low = 0.3
        self.gas_threshold = 300
        self.n_sensors_threshold = 3
        
    def fit(self, X, y=None):
        """Tune thresholds from training data percentiles."""
        if 'multimodal_anomaly_score' in X.columns:
            scores = X['multimodal_anomaly_score']
            self.threshold_low = scores.quantile(0.50)
            self.threshold_high = scores.quantile(0.80)
        if 'max_gas_response' in X.columns:
            self.gas_threshold = X['max_gas_response'].quantile(0.70)
        
    def predict(self, X):
        preds = []
        for _, row in X.iterrows():
            anom = row.get('multimodal_anomaly_score', 0)
            n_sens = row.get('n_sensors_above_baseline', 0)
            max_gas = row.get('max_gas_response', 0)
            
            if anom > self.threshold_high and n_sens >= self.n_sensors_threshold and max_gas > self.gas_threshold:
                preds.append(2)
            elif anom > self.threshold_low or max_gas > self.gas_threshold:
                preds.append(1)
            else:
                preds.append(0)
        return np.array(preds)
        
    def predict_proba(self, X):
        preds = self.predict(X)
        proba = np.zeros((len(preds), 3))
        for i, p in enumerate(preds):
            proba[i, p] = 0.8
            for j in range(3):
                if j != p:
                    proba[i, j] = 0.1
        return proba

def prepare_data(df, imputer=None, scaler=None, is_train=True):
    # Separate features and metadata
    feat_cols = [c for c in df.columns if c not in META_COLS and df[c].dtype in [np.float64, np.int64]]
    X = df[feat_cols]
    
    y = df['label'].map(LABEL_MAP).fillna(0).astype(int)
    
    if is_train:
        imputer = SimpleImputer(strategy='median')
        X_imp = imputer.fit_transform(X)
        scaler = StandardScaler()
        X_sc = scaler.fit_transform(X_imp)
    else:
        X_imp = imputer.transform(X)
        X_sc = scaler.transform(X_imp)
        
    X_processed = pd.DataFrame(X_sc, columns=X.columns, index=df.index)
    return X_processed, y, imputer, scaler, feat_cols

def train_and_evaluate():
    os.makedirs('data/models', exist_ok=True)
    os.makedirs('data/predictions', exist_ok=True)
    
    print("Loading datasets...")
    train_df = pd.read_csv('data/train.csv')
    val_df = pd.read_csv('data/validation.csv')
    test_df = pd.read_csv('data/test.csv')
    
    X_train, y_train, imputer, scaler, feature_cols = prepare_data(train_df, is_train=True)
    X_val, y_val, _, _, _ = prepare_data(val_df, imputer, scaler, is_train=False)
    X_test, y_test, _, _, _ = prepare_data(test_df, imputer, scaler, is_train=False)
    
    # Save preprocessors
    with open('data/models/preprocessors.pkl', 'wb') as f:
        pickle.dump({'imputer': imputer, 'scaler': scaler, 'features': feature_cols}, f)
        
    models = {
        'RuleBased': RuleBasedBaseline(),
        'LogisticRegression': LogisticRegression(max_iter=1000),
        'RandomForest': RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42)
    }
    
    # Try XGBoost
    try:
        from xgboost import XGBClassifier
        models['XGBoost'] = XGBClassifier(
            random_state=42, 
            use_label_encoder=False, 
            eval_metric='mlogloss',
            objective='multi:softprob',
            num_class=3
        )
    except ImportError:
        print("XGBoost not installed. Skipping XGBoost model.")

    print("\nTraining models...")
    for name, model in models.items():
        print(f"-> {name}")
        
        # Fit
        if name == 'RuleBased':
            # Rule based uses raw DataFrame to access column names easily
            model.fit(train_df) 
        else:
            model.fit(X_train, y_train)
            
        # Save model
        with open(f'data/models/{name}.pkl', 'wb') as f:
            pickle.dump(model, f)
            
        # Predict on Val and Test
        for split_name, df, X_split in [('val', val_df, X_val), ('test', test_df, X_test)]:
            if name == 'RuleBased':
                preds = model.predict(df)
                probs = model.predict_proba(df)
            else:
                preds = model.predict(X_split)
                probs = model.predict_proba(X_split) if hasattr(model, 'predict_proba') else None
                
            out_df = df[['event_id', 'session_id', 'label']].copy()
            out_df['pred_class'] = preds
            if probs is not None:
                out_df['prob_0'] = probs[:, 0]
                out_df['prob_1'] = probs[:, 1]
                out_df['prob_2'] = probs[:, 2]
                
            out_df.to_csv(f'data/predictions/{name}_{split_name}.csv', index=False)
            
    print("\nTraining complete.")

if __name__ == '__main__':
    train_and_evaluate()
