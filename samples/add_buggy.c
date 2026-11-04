/* Bug: negative numbers are treated as zero, and the result is wrong when both are negative. */
#include <stdio.h>

int add(int x, int y)
{
    if (x < 0) x = 0;     /* "we only add positive numbers" */
    if (y < 0) y = 0;
    return x + y;
}

int main(void)
{
    int x, y;
    scanf("%d %d", &x, &y);
    printf("%d\n", add(x, y));
    return 0;
}
