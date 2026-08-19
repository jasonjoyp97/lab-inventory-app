def set_custom_aesthetic():
    st.markdown(
        """
        <style>
        /* Main background - Softer dark slate for eye comfort */
        .stApp {
            background-color: #0E1117;
            color: #FAFAFA;
        }
        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background-color: #262730 !important;
        }
        /* Make tabs highly visible and readable */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background-color: transparent;
        }
        /* Inactive Tab Styling */
        .stTabs [data-baseweb="tab"] {
            background-color: #1E1E2E;
            border-radius: 6px 6px 0px 0px;
            padding: 10px 16px;
            color: #A6A6A6;
            border: 1px solid #333;
            border-bottom: none;
        }
        /* Hover effect for inactive tabs */
        .stTabs [data-baseweb="tab"]:hover {
            color: #FFFFFF;
            background-color: #2D2D44;
        }
        /* Active Tab Styling - Bright and bold */
        .stTabs [aria-selected="true"] {
            background-color: #3B3B58 !important;
            color: #FFFFFF !important;
            border-bottom: 3px solid #FF4B4B !important;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
