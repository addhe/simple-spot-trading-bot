def _validate_kline_data(kline):
    """Validate individual kline data point"""
    try:
        # Check data types and ranges
        float_values = [
            float(kline[1]),  # open
            float(kline[2]),  # high
            float(kline[3]),  # low
            float(kline[4]),  # close
            float(kline[5])   # volume
        ]

        # Validate price and volume
        if (
            float_values[1] >= float_values[3] and  # high >= close
            float_values[2] <= float_values[3] and  # low <= close
            float_values[5] >= 0  # volume non-negative
        ):
            return True

    except (ValueError, TypeError):
        pass

    return False