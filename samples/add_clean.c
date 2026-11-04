/*
 * add_clean.c - reads two integers and prints their sum.
 * Uses 64-bit arithmetic so that INT_MAX + 1 cannot overflow.
 */
#include <stdio.h>

/* Return the exact sum of two 32-bit integers. */
long long add(int lhs, int rhs)
{
    return (long long)lhs + (long long)rhs;
}

int main(void)
{
    int first, second;

    /* Read both operands; stop if the input is malformed. */
    if (scanf("%d %d", &first, &second) != 2) {
        return 1;
    }

    printf("%lld\n", add(first, second));
    return 0;
}
