"""
SkyPharma - Client Web Portal (Streamlit)
Interface Client pour la consultation et la commande de medicaments en temps reel.
Connectee a la base de donnees SQLite commune du robot ASRS.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import streamlit as st

# Configuration de la page
st.set_page_config(
    page_title="SkyPharma - Portail Client & Commande",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Chemins des fichiers
PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "data" / "asrs.db"
ASSETS_DIR = PROJECT_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "pharmacists_morocco_logo.png"

# Custom CSS pour une interface soignee et moderne
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1a5276;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #566573;
        margin-bottom: 1.5rem;
    }
    .card {
        background-color: #ffffff;
        padding: 1.2rem;
        border-radius: 10px;
        border: 1px solid #e1e8ed;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
    .stock-badge-in {
        background-color: #d4efdf;
        color: #196f3d;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .stock-badge-out {
        background-color: #fadbd8;
        color: #943126;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .metric-box {
        background: linear-gradient(135deg, #ebf5fb, #e8f8f5);
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        border: 1px solid #d4e6f1;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_connection():
    if not DB_PATH.exists():
        st.error(f"Base de données introuvable : {DB_PATH}")
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_medicines(query: str = "", category_filter: str = "Toutes"):
    conn = get_connection()
    if not conn:
        return []
    try:
        sql = "SELECT * FROM medicines WHERE is_active = 1"
        params = []
        if query:
            sql += " AND (name LIKE ? OR location_label LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        if category_filter and category_filter != "Toutes":
            sql += " AND category = ?"
            params.append(category_filter)
        sql += " ORDER BY name ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_categories():
    conn = get_connection()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM medicines WHERE is_active = 1 AND category IS NOT NULL AND category != ''"
        ).fetchall()
        return [r["category"] for r in rows]
    finally:
        conn.close()


def place_order(medicine_id: int, quantity: int = 1):
    conn = get_connection()
    if not conn:
        return False, "Connexion BD échouée"
    try:
        cur = conn.cursor()
        # Verifier le stock actuel
        cur.execute("SELECT * FROM medicines WHERE id = ? AND is_active = 1", (medicine_id,))
        med = cur.fetchone()
        if not med:
            return False, "Médicament introuvable"
        if med["stock"] < quantity:
            return False, f"Stock insuffisant (disponible: {med['stock']})"

        # Mettre a jour le stock
        cur.execute(
            "UPDATE medicines SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (quantity, medicine_id),
        )

        # Enregistrer la commande dans dispense_history
        cur.execute(
            """
            INSERT INTO dispense_history (medicine_id, medicine_name, x, y, status, message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                med["id"],
                med["name"],
                med["x"],
                med["y"],
                "CLIENT_ORDER_PLACED",
                f"Commande client web de {quantity} unité(s) - Emplacement: {med['location_label'] or 'N/A'}",
            ),
        )
        conn.commit()
        return True, f"Commande validée avec succès pour {quantity}x {med['name']} !"
    except Exception as exc:
        conn.rollback()
        return False, f"Erreur lors de la commande : {exc}"
    finally:
        conn.close()


def load_recent_orders(limit: int = 10):
    conn = get_connection()
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT id, medicine_name, x, y, status, message, created_at
            FROM dispense_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# --- SIDEBAR ---
with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=180)
    st.markdown("## 🤖 SkyPharma ASRS")
    st.markdown("**Plateforme Client Connectée**")
    st.markdown("Ce portail client est synchronisé en temps réel avec l'interface administrateur et le robot ASRS.")
    st.markdown("---")

    st.subheader("🔍 Filtres de recherche")
    search_query = st.text_input("Rechercher un médicament", placeholder="Ex: Doliprane, Paracetamol...")
    
    categories = ["Toutes"] + load_categories()
    selected_category = st.selectbox("Catégorie", categories)

    st.markdown("---")
    st.markdown("### ℹ️ Informations Système")
    st.info(
        """
        - **Robot**: Cartésien 3 axes H-Bot
        - **Contrôleur**: Arduino UNO + GRBL 1.1
        - **Stockage**: Matrice dynamique
        - **Synchronisation**: Base SQLite locale
        """
    )


# --- CORPS DE PAGE ---
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown('<div class="main-title">🏥 SkyPharma - Catalogue & Commande</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Commandez vos médicaments préparés automatiquement par le robot de dispensation ASRS</div>',
        unsafe_allow_html=True,
    )

with col_head2:
    if st.button("🔄 Actualiser le catalogue"):
        st.rerun()

# Recuperation des medicaments
medicines = load_medicines(query=search_query, category_filter=selected_category)

# Statistiques d'en-tete
total_meds = len(medicines)
in_stock_count = sum(1 for m in medicines if m["stock"] > 0)
total_units = sum(m["stock"] for m in medicines)

col_stat1, col_stat2, col_stat3 = st.columns(3)
with col_stat1:
    st.markdown(
        f'<div class="metric-box"><h4>📦 Références actives</h4><h2>{total_meds}</h2></div>',
        unsafe_allow_html=True,
    )
with col_stat2:
    st.markdown(
        f'<div class="metric-box"><h4>✅ Disponibles</h4><h2>{in_stock_count}</h2></div>',
        unsafe_allow_html=True,
    )
with col_stat3:
    st.markdown(
        f'<div class="metric-box"><h4>💊 Stock global</h4><h2>{total_units} unités</h2></div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# Onglets principaux
tab_catalogue, tab_orders, tab_architecture = st.tabs(["📋 Catalogue des Médicaments", "📦 Historique des Commandes", "⚙️ Architecture Robot & Démo"])

with tab_catalogue:
    if not medicines:
        st.warning("Aucun médicament trouvé correspondant à vos critères.")
    else:
        # Affichage en grille
        cols = st.columns(3)
        for idx, med in enumerate(medicines):
            with cols[idx % 3]:
                is_available = med["stock"] > 0
                badge_html = (
                    f'<span class="stock-badge-in">En Stock ({med["stock"]})</span>'
                    if is_available
                    else '<span class="stock-badge-out">Rupture de Stock</span>'
                )

                st.markdown(
                    f"""
                    <div class="card">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <h3 style="margin:0; color:#2c3e50;">{med['name']}</h3>
                            {badge_html}
                        </div>
                        <p style="margin:4px 0; color:#7f8c8d; font-size:0.9rem;">
                            <strong>Catégorie:</strong> {med.get('category') or 'Générique'}<br>
                            <strong>Emplacement:</strong> {med.get('location_label') or 'Casier automatique'}<br>
                            <strong>Coordonnées ASRS:</strong> X: {med['x']} mm | Y: {med['y']} mm<br>
                            <strong>Péremption:</strong> {med.get('expiry_date') or 'N/A'}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if is_available:
                    with st.expander(f"🛒 Commander {med['name']}", expanded=False):
                        qty = st.number_input(
                            "Quantité",
                            min_value=1,
                            max_value=max(1, med["stock"]),
                            value=1,
                            key=f"qty_{med['id']}",
                        )
                        if st.button("Valider la commande", key=f"btn_{med['id']}", type="primary"):
                            success, msg = place_order(med["id"], qty)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    st.button("Indisponible", key=f"dis_{med['id']}", disabled=True)

with tab_orders:
    st.subheader("📋 Dernières opérations & commandes enregistrées")
    recent_orders = load_recent_orders(limit=20)
    if recent_orders:
        st.dataframe(
            recent_orders,
            column_config={
                "id": "ID",
                "medicine_name": "Médicament",
                "x": "Pos X (mm)",
                "y": "Pos Y (mm)",
                "status": "Statut",
                "message": "Détails",
                "created_at": "Date & Heure",
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Aucune commande enregistrée pour le moment.")

with tab_architecture:
    st.subheader("🔬 Écosystème SkyPharma ASRS")
    st.markdown(
        """
        Le projet **SkyPharma** intègre une chaîne mécatronique et logicielle complète :
        1. **Interface Administrateur (PyQt6)** : Pilotage direct du robot (Homing, Jog, G-code), supervision du châssis, gestion des stocks et de la matrice de rangement.
        2. **Interface Client (Streamlit)** : Consultation dynamique du catalogue, synchronisation instantanée du stock et génération des ordres de prélèvement.
        3. **Noyau de Contrôle (Python & GRBL)** : Générateur de trajectoires sécurisées, client série asynchrone GRBL 1.1, automate d'états finis (FSM).
        4. **Robotique Cartésienne H-Bot** : Moteurs pas à pas NEMA 17, drivers DRV8825, carte Arduino UNO + CNC Shield V3, préhenseur électromécanique et capteurs de fin de course.
        5. **Sas de Distribution Automatisé** : Dépôt sécurisé des boîtes de médicaments pour remise au patient / personnel soignant.
        """
    )
