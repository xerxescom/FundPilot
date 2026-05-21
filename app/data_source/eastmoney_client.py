from app.data_source.akshare_client import AkshareFundDataSource


class EastmoneyFundDataSource(AkshareFundDataSource):
    """Placeholder fallback with the same normalized interface for v1."""

    source_name = "eastmoney"
