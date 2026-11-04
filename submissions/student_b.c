#include <stdio.h>

int main(void)
{
    long long total = 0;
    int count = 0, value;
    while (count < 2 && scanf("%d", &value) == 1) {
        total += value;
        count++;
    }
    printf("%lld\n", total);
    return 0;
}
