#include <stdio.h>

long long sum_two(int first, int second)
{
    return (long long)first + second;
}

int main(void)
{
    int first, second;
    if (scanf("%d %d", &first, &second) != 2)
        return 1;
    printf("%lld\n", sum_two(first, second));
    return 0;
}
