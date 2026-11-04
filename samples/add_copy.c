// my own solution :)
#include <stdio.h>
long long plus(int p, int q) { return (long long)p + q; }
int main(void) {
    int p, q;
    if (scanf("%d %d", &p, &q) != 2) return 1;
    printf("%lld\n", plus(p, q));
    return 0;
}
