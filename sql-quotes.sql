-- =====================================================
-- SQL Challenge: Get Last Quote per DocumentId
-- Author: Tu Nombre
-- Date: 2024
-- =====================================================

-- 1. ESTRUCTURA DE TABLA ASUMIDA
-- =====================================================
/*
Asumimos una tabla 'quotes' que almacena versiones de quotes
con soporte para múltiples actualizaciones por documento
*/
CREATE TABLE quotes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id VARCHAR(36) NOT NULL,
    quote_content TEXT NOT NULL,
    author VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    version INT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',
    
    -- Índices para optimización
    INDEX idx_document_id (document_id),
    INDEX idx_updated_at (updated_at),
    INDEX idx_document_updated (document_id, updated_at DESC),
    INDEX idx_document_updated_version (document_id, updated_at DESC, version DESC)
);

-- 2. QUERY PRINCIPAL (Optimizada para MySQL 8.0+)
-- =====================================================
WITH target_documents AS (
    -- Lista de 500 documentos (en producción usar tabla temporal)
    SELECT 'doc-001' AS document_id
    UNION ALL SELECT 'doc-002'
    UNION ALL SELECT 'doc-003'
    -- ... (500 documentos)
),
ranked_quotes AS (
    SELECT 
        q.id,
        q.document_id,
        q.quote_content,
        q.author,
        q.created_at,
        q.updated_at,
        q.version,
        ROW_NUMBER() OVER (
            PARTITION BY q.document_id 
            ORDER BY q.updated_at DESC, q.version DESC
        ) AS rn
    FROM quotes q
    INNER JOIN target_documents td ON q.document_id = td.document_id
    WHERE q.status = 'active'
)
SELECT 
    id,
    document_id,
    quote_content,
    author,
    created_at,
    updated_at,
    version
FROM ranked_quotes
WHERE rn = 1
ORDER BY document_id;

-- 3. GUÍA DE OPTIMIZACIÓN
-- =====================================================
/*
EXPLICACIÓN DE ÍNDICES:

1. idx_document_updated_version (document_id, updated_at DESC, version DESC)
   - ÍNDICE PRINCIPAL: Cubre toda la consulta
   - Permite particionar por document_id y ordenar por updated_at + version
   - Evita ordenamientos adicionales en memoria

2. idx_document_id (document_id)
   - ÍNDICE SECUNDARIO: Para búsquedas simples por documento

3. idx_updated_at (updated_at)
   - ÍNDICE SECUNDARIO: Para ordenamiento cuando no hay document_id

RECOMENDACIONES:
- Usar tabla temporal para los 500 IDs (más eficiente que IN con lista)
- Mantener estadísticas actualizadas: ANALYZE TABLE quotes;
- Monitorear con EXPLAIN para verificar uso de índices
- Considerar particionamiento por document_id si la tabla > 100M registros
*/

-- 4. VERIFICACIÓN DE RENDIMIENTO
-- =====================================================
-- Verificar que los índices se están usando
EXPLAIN
WITH ranked_quotes AS (
    SELECT 
        q.*,
        ROW_NUMBER() OVER (
            PARTITION BY q.document_id 
            ORDER BY q.updated_at DESC, q.version DESC
        ) AS rn
    FROM quotes q
    WHERE q.document_id IN ('doc-001', 'doc-002', 'doc-003')
)
SELECT * FROM ranked_quotes WHERE rn = 1;

-- 5. ALTERNATIVA PARA BASES DE DATOS ANTERIORES A MySQL 8.0
-- =====================================================
/*
Si el motor no soporta Window Functions, usar esta alternativa:
*/
SELECT 
    q.*
FROM quotes q
INNER JOIN (
    SELECT 
        document_id,
        MAX(updated_at) as last_updated,
        MAX(version) as last_version
    FROM quotes
    WHERE document_id IN ('doc-001', 'doc-002', 'doc-003')
    GROUP BY document_id
) latest ON q.document_id = latest.document_id
    AND q.updated_at = latest.last_updated
    AND q.version = latest.last_version
ORDER BY q.document_id;