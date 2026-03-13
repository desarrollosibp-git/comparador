import pandas as pd
import recordlinkage

def normalize_weights(raw_weights):
    defaults = {
        'curp': 0.55,
        'nombre': 0.25,
        'fecha_nacimiento': 0.20,
    }

    if not isinstance(raw_weights, dict):
        return defaults

    weights = {
        'curp': max(0.0, float(raw_weights.get('curp', defaults['curp']))),
        'nombre': max(0.0, float(raw_weights.get('nombre', defaults['nombre']))),
        'fecha_nacimiento': max(0.0, float(raw_weights.get('fecha_nacimiento', defaults['fecha_nacimiento']))),
    }

    total = weights['curp'] + weights['nombre'] + weights['fecha_nacimiento']
    if total <= 0:
        return defaults

    return {
        'curp': weights['curp'] / total,
        'nombre': weights['nombre'] / total,
        'fecha_nacimiento': weights['fecha_nacimiento'] / total,
    }

def match_records(data):
    dfA = pd.DataFrame(data.dataA)
    dfB = pd.DataFrame(data.dataB)

    required_cols = ['curp', 'nombre', 'fecha_nacimiento']
    for col in required_cols:
        if col not in dfA.columns:
            dfA[col] = ''
        if col not in dfB.columns:
            dfB[col] = ''

    for col in required_cols:
        dfA[col] = dfA[col].fillna('').astype(str)
        dfB[col] = dfB[col].fillna('').astype(str)

    # Normalizacion basica para evitar falsos negativos por formato.
    dfA['curp_norm'] = dfA['curp'].str.upper().str.replace(r'[^A-Z0-9]', '', regex=True)
    dfB['curp_norm'] = dfB['curp'].str.upper().str.replace(r'[^A-Z0-9]', '', regex=True)
    dfA['nombre_norm'] = dfA['nombre'].str.lower().str.strip()
    dfB['nombre_norm'] = dfB['nombre'].str.lower().str.strip()
    dfA['fecha_nacimiento_norm'] = dfA['fecha_nacimiento'].str.strip()
    dfB['fecha_nacimiento_norm'] = dfB['fecha_nacimiento'].str.strip()

    indexer = recordlinkage.Index()
    indexer.full()
    pairs = indexer.index(dfA, dfB)

    compare = recordlinkage.Compare()

    compare.string(
        'nombre_norm',
        'nombre_norm',
        method='jarowinkler',
        label='nombre_score'
    )

    compare.exact('curp_norm', 'curp_norm', label='curp_score')
    compare.exact('fecha_nacimiento_norm', 'fecha_nacimiento_norm', label='fecha_nacimiento_score')

    features = compare.compute(pairs, dfA, dfB)

    config = getattr(data, 'config', None)
    raw_weights = getattr(config, 'weights', None) if config is not None else None
    weights = normalize_weights(raw_weights)

    features['score_final'] = (
        features['curp_score'] * weights['curp'] +
        features['nombre_score'] * weights['nombre'] +
        features['fecha_nacimiento_score'] * weights['fecha_nacimiento']
    )

    results = features.reset_index().to_dict(orient="records")

    return results