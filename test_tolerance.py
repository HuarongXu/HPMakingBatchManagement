def _tolerance_band(value: float) -> float:
    \"\"\"根据MOQ大小返回对应的绝对容差值\"\"\"
    # 根据业务规范：4.4和2.2 MOQ的容差为±0.05，1.1 MOQ的容差为±0.02
    if abs(value - 1.1) < 0.001:  # value ≈ 1.1
        return 0.02
    elif abs(value - 2.2) < 0.001 or abs(value - 4.4) < 0.001:  # value ≈ 2.2 or 4.4
        return 0.05
    else:
        # 对于非标准值，找到最接近的标准值并使用其容差
        # 这样可以确保在使用乘数计算总容量时仍然使用正确的容差
        closest_standard = min([1.1, 2.2, 4.4], key=lambda x: abs(x - value))
        if abs(closest_standard - 1.1) < 0.001:
            return 0.02
        else:  # 2.2 or 4.4
            return 0.05

print('测试容差函数:')
print(f'_tolerance_band(1.1) = {_tolerance_band(1.1)}')  # 应该输出 0.02
print(f'_tolerance_band(2.2) = {_tolerance_band(2.2)}')  # 应该输出 0.05
print(f'_tolerance_band(4.4) = {_tolerance_band(4.4)}')  # 应该输出 0.05
print(f'_tolerance_band(6.6) = {_tolerance_band(6.6)}')  # 接近3×2.2，应该输出 0.05
print(f'_tolerance_band(8.8) = {_tolerance_band(8.8)}')  # 接近2×4.4，应该输出 0.05
print(f'_tolerance_band(3.3) = {_tolerance_band(3.3)}')  # 接近1.5×2.2，应该输出 0.05
print(f'_tolerance_band(5.5) = {_tolerance_band(5.5)}')  # 接近2.5×2.2，应该输出 0.05
