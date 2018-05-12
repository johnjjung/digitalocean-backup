#!/usr/bin/env python3

import argparse
import datetime
import json
import logging
import sys

import digitalocean

from dobackup import __basefilepath__, __version__

logging.basicConfig(
    format="%(asctime)s [%(levelname)-5.5s]  %(message)s",
    handlers=[
        logging.FileHandler(__basefilepath__ + "dobackup.log",
                            mode='a', encoding=None, delay=False),
        logging.StreamHandler(sys.stdout)
    ],
    level="INFO")
log = logging.getLogger()


def main():
    parser = argparse.ArgumentParser(
        description='Automated offline snapshots of digitalocean droplets')
    parser.add_argument('-v', '--version', action='version', version="dobackup " + __version__)
    parser.add_argument('--init', dest='init',
                        help='Save token to .token file', action='store_true')
    parser.add_argument('--list-all', dest='list_all',
                        help='List all droplets', action='store_true')
    parser.add_argument('--list-snaps', dest='list_snaps',
                        help='List all snapshots', action='store_true')
    parser.add_argument('--list-tagged', dest='list_tagged',
                        help='List droplets using "--tag-name"',
                        action='store_true')
    parser.add_argument('--list-tags', dest='list_tags',
                        help='List all used tags', action='store_true')
    parser.add_argument('--list-older-than', dest='list_older_than', type=int,
                        help='List snaps older than, in days')
    parser.add_argument('--tag-server', dest='tag_server', type=str,
                        help='Add tag to the provided droplet id')
    parser.add_argument('--untag', dest='untag', type=str,
                        help='Remove tag from the provided droplet id')
    parser.add_argument('--tag-name', dest='tag_name', type=str,
                        help='To be used with "--list-tags" and "--backup-all",\
                         default value is "auto-backup"', default='auto-backup')
    parser.add_argument('--delete-older-than', dest='delete_older_than',
                        type=int, help='Delete backups older than, in days')
    parser.add_argument('--backup', dest='backup', type=str,
                        help='Shutdown, Backup, Then Restart the given droplet using id')
    parser.add_argument('--backup-all', dest='backup_all',
                        help='Shutdown, Backup, Then Restart all droplets with "--tag-name"',
                        action='store_true')

    args = parser.parse_args()

    run(args.init, args.list_all, args.list_snaps, args.list_tagged,
        args.list_tags, args.list_older_than, args.tag_server, args.untag,
        args.tag_name, args.delete_older_than, args.backup, args.backup_all)


def set_token():
    token_str = input("Paste The Digital Ocean's Token to Be Stored In .token File : ")
    if len(token_str) != 64:
        log.error("Is It Really A Token Though? The Length Should Be 64")
        sys.exit()
    tocken_dic = {"token0": token_str}

    try:
        with open(__basefilepath__ + '.token', 'w') as token_file:
            json.dump(tocken_dic, token_file)
        log.info("The Token Has Been Stored In .token File")
    except FileNotFoundError:
        log.error("FileNotFoundError: SOMETHING WRONG WITH THE PATH TO '.token'")
        sys.exit()


def start_backup(droplet):
    snap_name = droplet.name + "--auto-backup--" + \
        str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # snap_name = droplet.name + "--auto-backup--2018-05-02 12:37:52"
    log.info("Powering Off : " + str(droplet))
    snap = (droplet.take_snapshot(snap_name, power_off=True))
    log.info("Powered Off " + str(droplet) + " Taking Snapshot")
    snap_action = droplet.get_action(snap["action"]["id"])
    return snap_action


def snap_completed(snap_action):
    snap_outcome = snap_action.wait(update_every_seconds=3)
    if snap_outcome:
        log.info(str(snap_action) + " Snapshot Completed")
        return True
    else:
        log.error("SNAPSHOT FAILED" + str(snap_action))
        return False


def turn_it_on(droplet):
    powered_up = droplet.power_on()
    if powered_up:
        log.info("Powered Back Up " + str(droplet))
    else:
        log.critical("DID NOT POWER UP " + str(droplet))


def find_old_backups(manager, older_than):
    old_snapshots = []
    last_backup_to_keep = datetime.datetime.now() - datetime.timedelta(days=older_than)

    for each_snapshot in manager.get_droplet_snapshots():
        # print(each_snapshot.name, each_snapshot.created_at, each_snapshot.id)
        if "--auto-backup--" in each_snapshot.name:
            backed_on = each_snapshot.name[each_snapshot.name.find("--auto-backup--") + 15:]
            # print("backed_on", backed_on)
            backed_on_date = datetime.datetime.strptime(backed_on, "%Y-%m-%d %H:%M:%S")
            if backed_on_date < last_backup_to_keep:
                old_snapshots.append(each_snapshot)
                print(each_snapshot)

    # print("OLD SNAPSHOTS", old_snapshots)
    return old_snapshots


def purge_backups(old_snapshots):
    if old_snapshots:   # list not empty
        for each_snapshot in old_snapshots:
            log.warning("Deleting Old Snapshot: " + str(each_snapshot))
            destroyed = each_snapshot.destroy()
            if destroyed:
                log.info("Successfully Destroyed The Snapshot")
            else:
                log.error("COULD NOT DESTROY SNAPSHOT " + str(each_snapshot))
    else:
        log.info("No Snapshot Is Old Enough To be Deleted")


def tag_droplet(do_token, droplet_id, tag_name):
    backup_tag = digitalocean.Tag(token=do_token, name=tag_name)
    backup_tag.create()  # create tag if not already created
    backup_tag.add_droplets([droplet_id])


def untag_droplet(do_token, droplet_id, tag_name):      # Currely broken
    backup_tag = digitalocean.Tag(token=do_token, name=tag_name)
    backup_tag.remove_droplets([droplet_id])


def list_droplets(manager):
    my_droplets = manager.get_all_droplets()
    log.info("Listing All Droplets:  <droplet-id>   <droplet-name>\n")
    for droplet in my_droplets:
        log.info(droplet)


def get_tagged(manager, tag_name):
    tagged_droplets = manager.get_all_droplets(tag_name=tag_name)
    return tagged_droplets


def list_snapshots(manager):
    all_snaps = manager.get_all_snapshots()
    log.info("All Available Snapshots Are : <snapshot-id>   <snapshot-name>\n")
    all_snaps.sort()
    for snap in all_snaps:
        log.info(snap)


def set_manager(do_token):
    manager = digitalocean.Manager(token=do_token)
    return manager


def get_token():
    try:
        with open(__basefilepath__ + '.token') as do_token_file:
            do_token = json.load(do_token_file)
            # print("token", do_token["token0"])
        return do_token["token0"]
    except FileNotFoundError:
        log.error("FileNotFoundError: PLEASE STORE THE DO ACCESS TOKEN USING '--init'")
        sys.exit()


def run(init, list_all, list_snaps, list_tagged, list_tags, list_older_than,
        tag_server, untag, tag_name, delete_older_than, backup, backup_all):
    log.info("-------------------------START-------------------------\n\n")
    if init:
        set_token()

    do_token = get_token()
    manager = set_manager(do_token)

    if list_all:
        list_droplets(manager)
    if list_snaps:
        list_snapshots(manager)
    if list_tagged:
        tagged_droplets = get_tagged(manager, tag_name=tag_name)
        log.info("Listing All The Tagged Droplets :")
        log.info(tagged_droplets)
    if list_tags:
        # Currently broken
        log.info("All Available Tags Are : " + str(manager.get_all_tags()))
    if tag_server:
        tag_droplet(do_token, tag_server, tag_name)
        tagged_droplets = get_tagged(manager, tag_name=tag_name)
        log.info("Now, Droplets Tagged With : " + tag_name + " Are :")
        log.info(tagged_droplets)
    if untag:   # broken
        untag_droplet(do_token, tag_server, tag_name)
        tagged_droplets = get_tagged(manager, tag_name=tag_name)
        log.info("Now, droplets tagged with : " + tag_name + " are :")
        log.info(tagged_droplets)
    if delete_older_than or delete_older_than == 0:     # even accept value 0
        log.info("Snapshots Older Than" + str(list_older_than) +
                 " Days, With '--auto-backup--' In Their Name Are :")
        old_backups = find_old_backups(manager, delete_older_than)
        purge_backups(old_backups)
        print("Delete them")
    if list_older_than or list_older_than == 0:
        log.info("Snapshots Older Than" + str(list_older_than) +
                 " Days, With '--auto-backup--' In Their Name Are :")
        find_old_backups(manager, list_older_than)
    if backup:
        droplet = manager.get_droplet(backup)
        snap_action = start_backup(droplet)
        snap_done = snap_completed(snap_action)
        turn_it_on(droplet)
        if not snap_done:
            log.error("SNAPSHOT FAILED " + str(snap_action) + str(droplet))
    if backup_all:
        snap_and_drop_ids = []   # stores all {"snap_action": snap_action, "droplet_id": droplet}
        tagged_droplets = get_tagged(manager, tag_name=tag_name)

        if tagged_droplets:  # doplets found with the --tag-name
            for drop in tagged_droplets:
                droplet = manager.get_droplet(drop.id)
                snap_action = start_backup(droplet)
                snap_and_drop_ids.append({"snap_action": snap_action, "droplet_id": droplet.id})
            log.info("Backups Started, snap_and_drop_ids:" + str(snap_and_drop_ids))
            for snap_id_pair in snap_and_drop_ids:
                snap_done = snap_completed(snap_id_pair["snap_action"])
                # print("snap_action and droplet_id", snap_id_pair)
                turn_it_on(manager.get_droplet(snap_id_pair["droplet_id"]))
                if not snap_done:
                    log.error("SNAPSHOT FAILED " + str(snap_action) + str(droplet))
        else:  # no doplets with the --tag-name
            log.warning("NO DROPLET FOUND WITH THE TAG NAME")
    log.info("---------------------------END----------------------------")
    log.info("\n\n")


if __name__ == '__main__':
    main()