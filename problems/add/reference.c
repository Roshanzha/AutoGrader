/* Reference solution (instructor's): uses 64-bit arithmetic so a + b never overflows. */
#include <stdio.h>

int main(void)
{
    long long a, b;
    if (scanf("%lld %lld", &a, &b) != 2) {
        return 1;
    }
    printf("%lld\n", a + b);
    return 0;
}
