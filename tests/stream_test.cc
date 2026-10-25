// Author: Ahmed Ahmed. Text protocol used only by the independent reference test.
#include <cstdio>
#include <cstdlib>
#include "branch.h"
#include "predictor.h"
#include "my_predictor.h"
int main(int argc,char **argv) {
    if(argc!=5) return 1;
    pm_predictor p(std::atoi(argv[1]),std::atoi(argv[2]),std::atoi(argv[3]),std::atoi(argv[4]));
    unsigned pc,flags,taken;
    while(std::scanf("%u %u %u",&pc,&flags,&taken)==3) {
        branch_info b{pc,0,flags}; auto *u=p.predict(b);
        const bool prediction=u->direction_prediction();
        const auto row=p.u.row, tag=p.u.tag, index=p.u.index; const int way=p.u.way;
        p.update(u,taken!=0,0);
        std::printf("%d %u %u %d %u %u %u\n",prediction,row,tag,way,p.history,
                    p.bimodal[index],p.lru[row]);
    }
}
