import streamlit as st
import pandas as pd
from fno_stocks import filter_fno_results


def render_fno_results(df, display_cols, style_fn, column_config):
    if df is None or df.empty:
        st.markdown('<div class="section-title">F&O Results · 0</div>', unsafe_allow_html=True)
        st.info("No F&O stocks from the current scan results.")
        return

    fno_df = filter_fno_results(df)
    st.markdown(f'<div class="section-title">F&O Results · {len(fno_df):,}</div>', unsafe_allow_html=True)
    if fno_df.empty:
        st.info("No F&O stocks from the current scan results.")
        return

    shown = fno_df[[c for c in display_cols if c in fno_df.columns]].copy()
    shown.insert(0, "S.No", range(1, len(shown) + 1))
    st.dataframe(shown.style.apply(style_fn, axis=1), use_container_width=True, hide_index=True, column_config=column_config)
