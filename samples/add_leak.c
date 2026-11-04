/* Correct answers, but leaks memory on every run (malloc without free). */
#include <stdio.h>
#include <stdlib.h>

long long add(int x, int y)
{
    return (long long)x + y;
}

int main(void)
{
    int x, y;
    int *scratch = malloc(4 * sizeof(int));   /* never freed */
    if (scanf("%d %d", &x, &y) != 2) {
        return 1;
    }
    scratch[0] = x;
    printf("%lld\n", add(scratch[0], y));
    return 0;
}
