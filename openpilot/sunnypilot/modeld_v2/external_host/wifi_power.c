// Minimal nl80211 GET/SET power-save diagnostic. No scan, reconnect or profile writes.
#include <linux/genetlink.h>
#include <linux/nl80211.h>
#include <net/if.h>
#include <sys/socket.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
struct message {struct nlmsghdr n;struct genlmsghdr g;unsigned char attrs[256];};
static void add(struct message* m,uint16_t kind,const void* data,size_t size){
 struct nlattr* a=(void*)((unsigned char*)m+m->n.nlmsg_len);a->nla_type=kind;a->nla_len=NLA_HDRLEN+size;memcpy((char*)a+NLA_HDRLEN,data,size);m->n.nlmsg_len+=NLA_ALIGN(a->nla_len);
}
static void init(struct message* m,int type,int command,int seq){memset(m,0,sizeof(*m));m->n.nlmsg_len=NLMSG_HDRLEN+GENL_HDRLEN;m->n.nlmsg_type=type;m->n.nlmsg_flags=NLM_F_REQUEST|NLM_F_ACK;m->n.nlmsg_seq=seq;m->g.cmd=command;m->g.version=1;}
static int exchange(int fd,struct message* m,int wanted){
 struct sockaddr_nl to={.nl_family=AF_NETLINK};if(sendto(fd,m,m->n.nlmsg_len,0,(void*)&to,sizeof(to))<0){perror("send");exit(1);}
 unsigned char data[65536];
 for(;;){int n=recv(fd,data,sizeof(data),0);if(n<0){perror("recv");exit(1);}for(struct nlmsghdr* h=(void*)data;NLMSG_OK(h,n);h=NLMSG_NEXT(h,n)){
  if(h->nlmsg_seq!=m->n.nlmsg_seq)continue;
  if(h->nlmsg_type==NLMSG_ERROR){struct nlmsgerr* e=NLMSG_DATA(h);if(e->error){errno=-e->error;perror("nl80211");exit(1);}if(!wanted)return 0;continue;}
  int remaining=h->nlmsg_len-NLMSG_HDRLEN-GENL_HDRLEN;struct nlattr* a=(void*)((char*)NLMSG_DATA(h)+GENL_HDRLEN);
  while(remaining>=NLA_HDRLEN&&a->nla_len>=NLA_HDRLEN&&a->nla_len<=remaining){
   if((a->nla_type&NLA_TYPE_MASK)==wanted){uint32_t result=0;size_t bytes=a->nla_len-NLA_HDRLEN;if(bytes!=2&&bytes!=4){fprintf(stderr,"unexpected attribute size\n");exit(1);}memcpy(&result,(char*)a+NLA_HDRLEN,bytes);return result;}
   int step=NLA_ALIGN(a->nla_len);remaining-=step;a=(void*)((char*)a+step);
  }
 }}
}
int main(int argc,char** argv){
 if(argc<2||argc>3||strcmp(argv[1],"wlan0")||(argc==3&&strcmp(argv[2],"on")&&strcmp(argv[2],"off"))){fprintf(stderr,"usage: wifi_power wlan0 [on|off]\n");return 2;}
 int fd=socket(AF_NETLINK,SOCK_RAW,NETLINK_GENERIC);if(fd<0){perror("socket");return 1;}struct timeval timeout={.tv_sec=3};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
 struct sockaddr_nl local={.nl_family=AF_NETLINK};if(bind(fd,(void*)&local,sizeof(local))<0){perror("bind");return 1;}
 struct message m;init(&m,GENL_ID_CTRL,CTRL_CMD_GETFAMILY,1);add(&m,CTRL_ATTR_FAMILY_NAME,"nl80211",8);int family=exchange(fd,&m,CTRL_ATTR_FAMILY_ID);
 uint32_t index=if_nametoindex("wlan0");if(!index){perror("interface");return 1;}
 if(argc==3){uint32_t state=!strcmp(argv[2],"on")?NL80211_PS_ENABLED:NL80211_PS_DISABLED;init(&m,family,NL80211_CMD_SET_POWER_SAVE,2);add(&m,NL80211_ATTR_IFINDEX,&index,4);add(&m,NL80211_ATTR_PS_STATE,&state,4);exchange(fd,&m,0);}
 init(&m,family,NL80211_CMD_GET_POWER_SAVE,3);add(&m,NL80211_ATTR_IFINDEX,&index,4);int state=exchange(fd,&m,NL80211_ATTR_PS_STATE);printf("%s\n",state==NL80211_PS_ENABLED?"on":"off");close(fd);return 0;
}
