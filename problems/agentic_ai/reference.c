#include <stdio.h>

int main(void)
{
    long long left, right;
    if (scanf("%lld %lld", &left, &right) != 2)
        return 1;

    long long sum = left + right;
    if (sum > 2147483647LL)
        sum -= 4294967296LL;
    else if (sum < -2147483648LL)
        sum += 4294967296LL;
    printf("%lld\n", sum);
    return 0;
}
